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


class SubmitPaymentProofView(generics.CreateAPIView):
    """POST /api/v1/transactions/my-payments/submit-proof/ — User submits receipt for an invoice."""
    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        proof_file = self.request.FILES.get("proof_file")

        final_proof_url = ""
        if proof_file:
            try:
                import cloudinary.uploader
                upload_res = cloudinary.uploader.upload(
                    proof_file,
                    folder="hasker/payment_proofs",
                    resource_type="image",
                )
                final_proof_url = upload_res.get("secure_url", "")
            except Exception as e:
                from rest_framework.exceptions import ValidationError
                raise ValidationError({"proof_file": f"Upload failed: {str(e)}"})

        import json as _json
        raw_allocated = self.request.data.get("allocated_items", "[]")
        try:
            allocated_items = _json.loads(raw_allocated) if isinstance(raw_allocated, str) else list(raw_allocated)
        except (ValueError, TypeError):
            allocated_items = []

        serializer.save(
            proof_image=final_proof_url,
            status="PENDING_VERIFICATION",
            allocated_items=allocated_items,
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
