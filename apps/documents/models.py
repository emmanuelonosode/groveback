from django.db import models
from cloudinary.models import CloudinaryField


class DocumentType(models.TextChoices):
    CONTRACT = "CONTRACT", "Contract"
    RECEIPT = "RECEIPT", "Receipt"
    AGREEMENT = "AGREEMENT", "Agreement"
    ID_DOCUMENT = "ID_DOCUMENT", "ID Document"
    PROOF_OF_FUNDS = "PROOF_OF_FUNDS", "Proof of Funds"
    OTHER = "OTHER", "Other"


class ClientDocument(models.Model):
    client = models.ForeignKey(
        "crm.Client",
        on_delete=models.CASCADE,
        related_name="documents",
    )
    name = models.CharField(max_length=200)
    file = CloudinaryField("file", resource_type="raw")
    document_type = models.CharField(max_length=20, choices=DocumentType.choices, default=DocumentType.OTHER)
    is_signed = models.BooleanField(default=False)
    uploaded_by = models.ForeignKey(
        "accounts.CustomUser",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="uploaded_documents",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Client Document"
        verbose_name_plural = "Client Documents"

    def __str__(self):
        return f"{self.name} ({self.get_document_type_display()}) — {self.client}"
