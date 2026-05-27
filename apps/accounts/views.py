from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from .models import CustomUser, Role
from .serializers import MeSerializer, PublicAgentSerializer, RegisterSerializer, VerifyEmailSerializer, ResendOTPSerializer, ChangePasswordSerializer
from .permissions import IsAdmin


class MeView(generics.RetrieveUpdateAPIView):
    """GET/PATCH /api/v1/auth/me/ — current user profile."""
    serializer_class = MeSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


class AgentListView(generics.ListAPIView):
    """GET /api/v1/agents/ — public agent directory."""
    serializer_class = PublicAgentSerializer
    permission_classes = [permissions.AllowAny]
    queryset = CustomUser.objects.filter(role=Role.AGENT, is_active=True).select_related("agent_profile")


class AgentDetailView(generics.RetrieveAPIView):
    """GET /api/v1/agents/{id}/ — public agent profile."""
    serializer_class = PublicAgentSerializer
    permission_classes = [permissions.AllowAny]
    queryset = CustomUser.objects.filter(role=Role.AGENT, is_active=True).select_related("agent_profile")


class RegisterView(generics.CreateAPIView):
    """POST /api/v1/auth/register/ — create a CLIENT account and return JWT tokens (No, now sends OTP)."""
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        user.generate_verification_code()

        # ── Admin alert: registration started ────────────────────────────────
        import threading
        def _alert_reg_started():
            try:
                from apps.notifications.tasks import send_admin_alert
                send_admin_alert(
                    f"Registration Started — {user.email}",
                    [
                        ("Email",      user.email),
                        ("Name",       user.get_full_name() or "—"),
                        ("IP Address", request.META.get("REMOTE_ADDR", "—")),
                        ("Step",       "Account created — awaiting email verification"),
                    ],
                )
            except Exception:
                pass
        threading.Thread(target=_alert_reg_started, daemon=True).start()

        return Response(
            {
                "message": "Account created successfully. Please check your email for the verification code.",
                "email": user.email,
            },
            status=status.HTTP_201_CREATED,
        )


class VerifyEmailView(generics.GenericAPIView):
    """POST /api/v1/auth/verify-email/"""
    serializer_class = VerifyEmailSerializer
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        email = serializer.validated_data["email"]
        code = serializer.validated_data["code"]
        
        try:
            user = CustomUser.objects.get(email=email)
        except CustomUser.DoesNotExist:
            return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)
            
        success, message = user.verify_code(code)
        
        if success:
            refresh = RefreshToken.for_user(user)

            # ── Admin alert: registration completed ──────────────────────────
            import threading
            def _alert_reg_complete():
                try:
                    from apps.notifications.tasks import send_admin_alert
                    from django.utils.timezone import now
                    send_admin_alert(
                        f"Registration Completed — {user.email}",
                        [
                            ("Email",        user.email),
                            ("Name",         user.get_full_name() or "—"),
                            ("Role",         user.role),
                            ("Verified At",  now().strftime("%B %d, %Y at %I:%M %p UTC")),
                            ("IP Address",   request.META.get("REMOTE_ADDR", "—")),
                        ],
                    )
                except Exception:
                    pass
            threading.Thread(target=_alert_reg_complete, daemon=True).start()

            return Response(
                {
                    "message": message,
                    "access": str(refresh.access_token),
                    "refresh": str(refresh),
                    "user": {
                        "id": user.id,
                        "email": user.email,
                        "first_name": user.first_name,
                        "last_name": user.last_name,
                        "full_name": user.full_name,
                        "role": user.role,
                        "is_email_verified": user.is_email_verified,
                        "onboarding_completed": user.onboarding_completed,
                    },
                },
                status=status.HTTP_200_OK,
            )
        else:
            return Response({"error": message}, status=status.HTTP_400_BAD_REQUEST)


class ChangePasswordView(generics.GenericAPIView):
    """POST /api/v1/auth/change-password/"""
    serializer_class   = ChangePasswordSerializer
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        s = self.get_serializer(data=request.data, context={"request": request})
        s.is_valid(raise_exception=True)
        request.user.set_password(s.validated_data["new_password"])
        request.user.save(update_fields=["password"])
        return Response({"detail": "Password updated successfully."})


class ResendOTPView(generics.GenericAPIView):
    """POST /api/v1/auth/resend-otp/"""
    serializer_class = ResendOTPSerializer
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        email = serializer.validated_data["email"]
        
        try:
            user = CustomUser.objects.get(email=email)
        except CustomUser.DoesNotExist:
            return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)
            
        if user.is_email_verified:
            return Response({"error": "Email is already verified."}, status=status.HTTP_400_BAD_REQUEST)
            
        user.generate_verification_code()
        
        return Response(
            {
                "message": "Verification code resent successfully.",
                "email": user.email,
            },
            status=status.HTTP_200_OK,
        )
