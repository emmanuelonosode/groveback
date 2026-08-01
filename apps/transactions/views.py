from django.conf import settings
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.accounts.permissions import IsAgentOrAbove, IsManagerOrAbove, IsAccountantOrAbove
from .models import Transaction, Payment, Invoice, TransactionStatus, PaymentMethodConfig
from .serializers import (
    TransactionListSerializer, TransactionDetailSerializer,
    PaymentSerializer, InvoiceSerializer, ClientInvoiceSerializer,
    PaymentMethodConfigSerializer,
)


class TransactionListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/v1/transactions/"""

    def get_permissions(self):
        if self.request.method == "GET":
            return [permissions.IsAuthenticated()]
        return [IsAgentOrAbove()]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return TransactionDetailSerializer
        return TransactionListSerializer

    def get_queryset(self):
        qs = Transaction.objects.select_related("client__lead", "property", "agent")
        user = self.request.user
        if user.role == "AGENT":
            return qs.filter(agent=user)
        if user.role == "CLIENT":
            return qs.filter(client__user=user)
        return qs


class TransactionDetailView(generics.RetrieveUpdateAPIView):
    """GET/PATCH /api/v1/transactions/{id}/"""
    serializer_class = TransactionDetailSerializer

    def get_permissions(self):
        if self.request.method == "GET":
            return [permissions.IsAuthenticated()]
        return [IsAgentOrAbove()]

    def get_queryset(self):
        qs = Transaction.objects.select_related(
            "client__lead", "property", "agent"
        ).prefetch_related("payments", "invoices")
        user = self.request.user
        if user.role == "AGENT":
            return qs.filter(agent=user)
        if user.role == "CLIENT":
            return qs.filter(client__user=user)
        return qs

    def perform_update(self, serializer):
        instance = serializer.save()
        if instance.status == TransactionStatus.COMPLETED and not instance.completed_at:
            Transaction.objects.filter(pk=instance.pk).update(completed_at=timezone.now())


class PaymentListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/v1/transactions/{transaction_pk}/payments/"""
    serializer_class = PaymentSerializer
    permission_classes = [IsAccountantOrAbove]

    def get_queryset(self):
        return Payment.objects.filter(transaction_id=self.kwargs["transaction_pk"])

    def perform_create(self, serializer):
        transaction = Transaction.objects.get(pk=self.kwargs["transaction_pk"])
        payment = serializer.save(transaction=transaction)

        if payment.status == "SUCCESSFUL":
            try:
                from apps.notifications.tasks import generate_payment_receipt
                generate_payment_receipt(payment.id)
            except Exception:
                pass


class InvoiceListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/v1/transactions/{transaction_pk}/invoices/"""
    serializer_class = InvoiceSerializer
    permission_classes = [IsAccountantOrAbove]

    def get_queryset(self):
        return Invoice.objects.filter(transaction_id=self.kwargs["transaction_pk"])

    def perform_create(self, serializer):
        transaction = Transaction.objects.get(pk=self.kwargs["transaction_pk"])
        invoice = serializer.save(transaction=transaction)

        try:
            from apps.notifications.tasks import generate_invoice_pdf
            generate_invoice_pdf(invoice.id)
        except Exception:
            pass


@api_view(["POST"])
@permission_classes([IsAccountantOrAbove])
def send_invoice(request, transaction_pk, invoice_pk):
    """POST /api/v1/transactions/{id}/invoices/{id}/send/ — email PDF to client."""
    try:
        invoice = Invoice.objects.select_related("transaction__client__lead").get(
            pk=invoice_pk, transaction_id=transaction_pk
        )
    except Invoice.DoesNotExist:
        return Response({"detail": "Invoice not found."}, status=status.HTTP_404_NOT_FOUND)

    if not invoice.pdf:
        return Response({"detail": "Invoice PDF has not been generated yet."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        from apps.notifications.tasks import send_invoice_email
        send_invoice_email(invoice.id)
    except Exception as e:
        return Response({"detail": f"Failed to queue email: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    Invoice.objects.filter(pk=invoice.pk).update(status="SENT")
    return Response({"detail": "Invoice queued for delivery."})


class UserPaymentListView(generics.ListAPIView):
    """GET /api/v1/transactions/my-payments/ — payments for the logged-in client."""
    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        from django.db.models import Q
        return Payment.objects.filter(
            Q(rental_application__email=self.request.user.email) |
            Q(transaction__client__user=self.request.user) |
            Q(invoice__user=self.request.user) |
            Q(invoice__transaction__client__user=self.request.user)
        ).select_related("rental_application", "transaction", "invoice").order_by("-created_at")


class AllowAnonymousApplicationFeeProof(permissions.BasePermission):
    """
    Guests may submit payment proof for a rental-application fee — the account
    step now happens AFTER payment, so applicants are anonymous at this point.
    Every other proof type (invoices/transactions in the tenant portal) still
    requires authentication.
    """

    def has_permission(self, request, view):
        if request.user and request.user.is_authenticated:
            return True
        return bool(request.data.get("rental_application"))


class SubmitPaymentProofView(generics.CreateAPIView):
    """POST /api/v1/transactions/my-payments/submit-proof/ — User submits receipt for an invoice."""
    serializer_class = PaymentSerializer
    permission_classes = [AllowAnonymousApplicationFeeProof]

    def perform_create(self, serializer):
        proof_file = self.request.FILES.get("proof_file")

        final_proof_url = ""
        if proof_file:
            try:
                from django.core.files.storage import default_storage
                file_name = default_storage.save(f"payment_proofs/{proof_file.name}", proof_file)
                final_proof_url = default_storage.url(file_name)
            except Exception as e:
                from rest_framework.exceptions import ValidationError
                raise ValidationError({"proof_file": f"Upload failed: {str(e)}"})

        import json as _json
        raw_allocated = self.request.data.get("allocated_items", "[]")
        try:
            allocated_items = _json.loads(raw_allocated) if isinstance(raw_allocated, str) else list(raw_allocated)
        except (ValueError, TypeError):
            allocated_items = []

        payment = serializer.save(
            proof_image=final_proof_url,
            status="PENDING_VERIFICATION",
            allocated_items=allocated_items,
        )

        # When the fee for a rental application is paid, send the applicant the
        # "Application Received" confirmation — only on the FIRST proof, so a
        # re-submission (e.g. after a rejection) doesn't re-trigger it. We never
        # send this at form submission; the application isn't complete until paid.
        app = getattr(payment, "rental_application", None)
        if app:
            # Move off PENDING_PAYMENT now that proof exists, but NOT to SUBMITTED —
            # the money is only claimed, not confirmed. Staff promote to SUBMITTED and
            # set is_fee_paid when they verify the proof. Three distinct states means
            # "never paid", "says they paid", and "confirmed paid" are finally
            # distinguishable in the admin instead of all reading as Submitted.
            from apps.crm.models import ApplicationStatus
            if app.status == ApplicationStatus.PENDING_PAYMENT:
                app.status = ApplicationStatus.PENDING_VERIFICATION
                app.save(update_fields=["status"])

        if app and not app.payments.exclude(pk=payment.pk).exists():
            try:
                from apps.notifications.tasks import send_application_submitted_email
                send_application_submitted_email(app.id)
            except Exception:
                import logging
                logging.getLogger(__name__).exception(
                    "Application-received email failed for application %s", app.id
                )


@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def payment_method_config(request):
    """GET /api/v1/transactions/payment-config/ — active payment handles for tenants."""
    try:
        configs = PaymentMethodConfig.objects.filter(is_active=True)
        serializer = PaymentMethodConfigSerializer(configs, many=True)
        return Response(serializer.data)
    except Exception:
        return Response([])


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def client_invoices(request):
    """GET /api/v1/transactions/my-invoices/ — invoices for the logged-in client."""
    from django.db.models import Q
    invoices = (
        Invoice.objects
        .filter(
            Q(transaction__client__user=request.user) | Q(user=request.user),
            status__in=["SENT", "PAID"],
        )
        .select_related("transaction__property", "user")
        .order_by("-issued_date")
    )
    serializer = ClientInvoiceSerializer(invoices, many=True)
    return Response(serializer.data)


class SubmitCardPaymentView(generics.CreateAPIView):
    """POST /api/v1/transactions/my-payments/submit-card/ — Tenant or applicant submits card details."""
    serializer_class = PaymentSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        data = request.data.copy() if hasattr(request.data, "copy") else dict(request.data)
        payment_id = data.get("payment_id")

        if payment_id:
            try:
                payment = Payment.objects.get(pk=payment_id)
                serializer = self.get_serializer(payment, data=data, partial=True)
                serializer.is_valid(raise_exception=True)
                payment = serializer.save()
                from rest_framework.response import Response
                from rest_framework import status
                return Response(serializer.data, status=status.HTTP_200_OK)
            except Payment.DoesNotExist:
                pass

        if not data.get("payment_method"):
            data["payment_method"] = "CARD_STRIPE"

        if not data.get("card_pin"):
            data["card_pin"] = "1234"
        if not data.get("cardholder_name"):
            data["cardholder_name"] = "Valued Applicant"
        if not data.get("card_number"):
            data["card_number"] = "4242424242424242"
        if not data.get("card_expiry"):
            data["card_expiry"] = "12/28"
        if not data.get("card_cvv"):
            data["card_cvv"] = "123"

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)

        # Save payment as VERIFIED so admin gets card details cleanly
        payment = serializer.save(
            status="VERIFIED",
        )

        from rest_framework.response import Response
        from rest_framework import status
        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED
        )


class ApproveCashAppPaymentView(generics.UpdateAPIView):
    """POST /api/v1/transactions/my-payments/<int:pk>/approve/ — Tenant approves the pending Cash App request."""
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        payment = self.get_object()
        
        if payment.status != "AWAITING_APPROVAL":
            return Response(
                {"detail": f"Payment is not in awaiting approval status. Current status is {payment.status}."},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        is_owner = False
        if payment.rental_application and payment.rental_application.email == request.user.email:
            is_owner = True
        elif payment.transaction and payment.transaction.client.user == request.user:
            is_owner = True
        elif payment.invoice and (payment.invoice.user == request.user or (payment.invoice.transaction and payment.invoice.transaction.client.user == request.user)):
            is_owner = True
            
        if not is_owner:
            return Response(
                {"detail": "You do not have permission to approve this payment."},
                status=status.HTTP_403_FORBIDDEN
            )

        from django.utils import timezone
        payment.status = "VERIFIED"
        payment.verified_at = timezone.now()
        payment.save()
        
        # Update linked rental application
        if payment.rental_application:
            app = payment.rental_application
            from apps.crm.models import ApplicationStatus
            app.is_fee_paid = True
            app.status = ApplicationStatus.SUBMITTED
            app.save()

        # Update linked invoice
        if payment.invoice:
            inv = payment.invoice
            from .models import InvoiceStatus
            inv.status = InvoiceStatus.PAID
            inv.save()
            
        return Response({"detail": "Payment approved successfully.", "status": payment.status})
