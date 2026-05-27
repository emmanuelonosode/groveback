from rest_framework import serializers
from .models import Payment, Transaction, Invoice, PaymentMethodConfig

class PaymentSerializer(serializers.ModelSerializer):
    proof_file = serializers.FileField(write_only=True, required=False, allow_empty_file=False)

    class Meta:
        model = Payment
        fields = [
            "id", "transaction", "rental_application", "invoice", "amount",
            "payment_method", "status", "reference_id", "proof_image", "proof_file",
            "verified_by", "verified_at", "rejection_reason", "paid_at",
            "receipt_sent", "receipt_pdf", "notes", "allocated_items", "created_at",
        ]
        read_only_fields = ["id", "status", "verified_by", "verified_at", "rejection_reason", "paid_at", "created_at"]

    def create(self, validated_data):
        validated_data.pop("proof_file", None)
        return super().create(validated_data)

class TransactionListSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source="client.lead.full_name", read_only=True)
    property_title = serializers.CharField(source="property.title", read_only=True)
    agent_name = serializers.CharField(source="agent.full_name", read_only=True)

    class Meta:
        model = Transaction
        fields = [
            "id", "client", "client_name", "property", "property_title",
            "agent", "agent_name", "transaction_type", "agreed_price",
            "status", "created_at"
        ]

class TransactionDetailSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source="client.lead.full_name", read_only=True)
    property_title = serializers.CharField(source="property.title", read_only=True)
    agent_name = serializers.CharField(source="agent.full_name", read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)

    class Meta:
        model = Transaction
        fields = "__all__"
        read_only_fields = ["created_at", "updated_at", "completed_at"]

class InvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invoice
        fields = "__all__"
        read_only_fields = ["invoice_number", "created_at"]

class PaymentMethodConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentMethodConfig
        fields = [
            "method",
            "display_name",
            "handle",
            "extra_instructions",
            # Bank transfer fields
            "recipient_name",
            "bank_name",
            "account_type",
            "account_number",
            "routing_number",
            "swift_bic",
            "bank_address",
            "recipient_address",
        ]


class ClientInvoiceSerializer(serializers.ModelSerializer):
    property_title = serializers.SerializerMethodField()
    property_address = serializers.SerializerMethodField()
    transaction_type = serializers.SerializerMethodField()

    def get_property_title(self, obj):
        if obj.transaction and obj.transaction.property:
            return obj.transaction.property.title
        return ""

    def get_property_address(self, obj):
        p = obj.transaction.property if obj.transaction else None
        if p:
            parts = [p.address, p.city, p.state]
            return ", ".join(x for x in parts if x)
        return ""

    def get_transaction_type(self, obj):
        return obj.transaction.transaction_type if obj.transaction else ""

    class Meta:
        model = Invoice
        fields = [
            "id", "invoice_number", "title", "description",
            "issued_date", "due_date", "line_items",
            "subtotal", "tax_rate", "tax_amount", "total",
            "status", "pdf", "created_at",
            "property_title", "property_address", "transaction_type",
        ]
