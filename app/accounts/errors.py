from app.core.errors import DomainError


class AuthenticationError(DomainError):
    status = 401
    code = "authentication_required"
    title = "Sign in required"


class InvalidSessionError(AuthenticationError):
    code = "invalid_session"
    title = "Session expired or revoked"

    def __init__(self) -> None:
        super().__init__(
            headers={
                "Set-Cookie": (
                    "__Host-docqa_session=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=lax"
                )
            }
        )


class InvalidCredentialsError(AuthenticationError):
    code = "invalid_credentials"
    title = "Email or password is incorrect"


class CsrfError(DomainError):
    status = 403
    code = "csrf_failed"
    title = "Request origin or CSRF token is invalid"


class EmailVerificationRequiredError(DomainError):
    status = 403
    code = "email_verification_required"
    title = "Verify your email before uploading documents"


class AccountUnavailableError(DomainError):
    status = 503
    code = "account_service_unavailable"
    title = "Account service is temporarily unavailable"


class WeakPasswordError(DomainError):
    status = 400
    code = "weak_password"
    title = "Use at least 8 characters, including a letter and a number"


class InvalidTokenError(DomainError):
    status = 400
    code = "invalid_token"
    title = "This link has expired or has already been used"


class PasswordMismatchError(DomainError):
    status = 400
    code = "password_mismatch"
    title = "Passwords do not match"
