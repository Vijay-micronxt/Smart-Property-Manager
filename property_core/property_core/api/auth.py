"""
Customer-facing authentication API for Smart Property Manager.

All endpoints use token-based auth (api_key:api_secret) — no browser
redirects, no Frappe Desk pages, no session-cookie flows.

Frappe endpoint base URL:
    /api/method/property_core.api.auth.<function_name>

Authenticated requests must include:
    Authorization: token <api_key>:<api_secret>
"""

import random
import string

import frappe
from frappe.utils.password import (
    check_password,
    remove_encrypted_password,
    set_encrypted_password,
    update_password,
)

from property_core.api.utils import ok

APP_NAME = "Smart Property Manager"
_OTP_PREFIX = "spm_pwd_reset_otp"
_OTP_TTL = 600  # 10 minutes


# ---------------------------------------------------------------------------
# 1. login
# ---------------------------------------------------------------------------

@frappe.whitelist(allow_guest=True)
def login(usr, pwd):
    """
    Authenticate a customer and return api_key + api_secret for token auth.

    Args:
        usr (str): Customer email address (Frappe User name).
        pwd (str): Password.

    Returns:
        dict: ok(data={user, full_name, api_key, api_secret})

    Raises:
        frappe.AuthenticationError: on invalid credentials.
    """
    try:
        login_manager = frappe.auth.LoginManager()
        login_manager.authenticate(user=usr, pwd=pwd)
        login_manager.post_login()
    except frappe.AuthenticationError:
        frappe.throw("Invalid email or password", frappe.AuthenticationError)

    return get_token()


# ---------------------------------------------------------------------------
# 2. get_token
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_token():
    """
    Generate or refresh api_key/api_secret for the current session user.

    Applies Frappe encrypted-password bug workaround: always removes any
    stale api_secret row (encrypted=0) before writing the new encrypted value
    so that get_decrypted_password can reliably retrieve it afterwards.

    Returns:
        dict: ok(data={user, full_name, api_key, api_secret})
    """
    user = frappe.session.user

    # Ensure api_key exists; create one if missing
    api_key = frappe.db.get_value("User", user, "api_key")
    if not api_key:
        api_key = frappe.generate_hash(length=15)
        frappe.db.set_value("User", user, "api_key", api_key)

    # Always generate a fresh api_secret on each token request
    api_secret = frappe.generate_hash(length=15)

    # Frappe bug workaround: delete any stale unencrypted row before inserting
    # the new one, otherwise get_decrypted_password silently returns None.
    remove_encrypted_password("User", user, fieldname="api_secret")
    set_encrypted_password("User", user, api_secret, fieldname="api_secret")
    frappe.db.commit()

    full_name = frappe.db.get_value("User", user, "full_name") or user

    return ok(
        data={
            "user": user,
            "full_name": full_name,
            "api_key": api_key,
            "api_secret": api_secret,
        }
    )


# ---------------------------------------------------------------------------
# 3. logout
# ---------------------------------------------------------------------------

@frappe.whitelist()
def logout():
    """
    Invalidate the current session.

    Returns:
        dict: ok(message="Logged out successfully")
    """
    frappe.local.login_manager.logout()
    return ok(message="Logged out successfully")


# ---------------------------------------------------------------------------
# 4. get_logged_in_user
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_logged_in_user():
    """
    Return the profile of the currently authenticated user.

    Returns:
        dict: ok(data={full_name, email, mobile_no, user_image, roles})
    """
    user = frappe.session.user
    doc = frappe.get_doc("User", user)
    return ok(
        data={
            "full_name": doc.full_name,
            "email": doc.email,
            "mobile_no": doc.mobile_no,
            "user_image": doc.user_image,
            "roles": frappe.get_roles(user),
        }
    )


# ---------------------------------------------------------------------------
# 5. change_password
# ---------------------------------------------------------------------------

@frappe.whitelist()
def change_password(old_password, new_password):
    """
    Change password for a logged-in user who knows their current password.

    No OTP required — verifies the existing password directly.

    Args:
        old_password (str): The user's current password.
        new_password (str): The desired new password.

    Returns:
        dict: ok(message="Password changed successfully")

    Raises:
        frappe.AuthenticationError: if old_password is wrong.
    """
    user = frappe.session.user
    try:
        check_password(user, old_password)
    except frappe.AuthenticationError:
        frappe.throw("Current password is incorrect", frappe.AuthenticationError)

    update_password(user=user, pwd=new_password)
    return ok(message="Password changed successfully")


# ---------------------------------------------------------------------------
# 6. forgot_password
# ---------------------------------------------------------------------------

@frappe.whitelist(allow_guest=True)
def forgot_password(usr, channel=None):
    """
    Initiate OTP-based password reset. Always returns a generic message
    regardless of whether the account exists to prevent account enumeration.

    Args:
        usr (str): The customer's email address.
        channel (str, optional): "email" forces email delivery;
            anything else (or None) tries WhatsApp first if available.

    Returns:
        dict: ok(message=<generic>, data={channel: <channel_used>})
    """
    generic_message = f"If an account exists for {usr}, a reset code has been sent."
    channel_used = channel or "email"

    try:
        if frappe.db.exists("User", {"name": usr, "enabled": 1}):
            otp = "".join(random.choices(string.digits, k=6))
            cache_key = f"{_OTP_PREFIX}:{usr}"
            frappe.cache().set_value(cache_key, otp, expires_in_sec=_OTP_TTL)
            channel_used, _ = _deliver_otp(usr, otp, channel)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "SPM forgot_password error")

    return ok(message=generic_message, data={"channel": channel_used})


# ---------------------------------------------------------------------------
# 7. reset_password
# ---------------------------------------------------------------------------

@frappe.whitelist(allow_guest=True)
def reset_password(usr, otp, new_password):
    """
    Validate OTP and set a new password. Logs out all existing sessions.

    Args:
        usr (str): The customer's email address.
        otp (str): The 6-digit code sent to the customer.
        new_password (str): The new password to set.

    Returns:
        dict: ok(message="Password reset successfully")

    Raises:
        frappe.ValidationError: if OTP is invalid or expired.
    """
    cache_key = f"{_OTP_PREFIX}:{usr}"
    cached_otp = frappe.cache().get_value(cache_key)

    if not cached_otp or str(cached_otp) != str(otp):
        frappe.throw("Invalid or expired code. Please request a new one.")

    update_password(user=usr, pwd=new_password, logout_all_sessions=True)
    frappe.cache().delete_value(cache_key)
    return ok(message="Password reset successfully")


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _deliver_otp(usr, otp, channel=None):
    """
    Send the OTP to the customer via WhatsApp (preferred) or email (fallback).

    Channel selection:
      1. channel == "email"  → skip to email directly.
      2. Otherwise, look up mobile_no from the Frappe User record.
      3. If mobile found and Property Core Settings.whatsapp_enabled == 1,
         create a WhatsApp Message doc and return; fall through on failure.
      4. Email fallback via frappe.sendmail().

    Args:
        usr (str): Frappe User name (email).
        otp (str): The 6-digit OTP string.
        channel (str, optional): "email" forces email; else tries WhatsApp first.

    Returns:
        tuple: (channel_used: str, sent_to: str)
    """
    message = (
        f"Your {APP_NAME} password reset code is {otp}. "
        f"It expires in 10 minutes."
    )

    if channel != "email":
        mobile = frappe.db.get_value("User", usr, "mobile_no")
        if mobile:
            try:
                settings = frappe.get_single("Property Core Settings")
                if getattr(settings, "whatsapp_enabled", False):
                    wa = frappe.new_doc("WhatsApp Message")
                    wa.to = mobile
                    wa.message = message
                    wa.insert(ignore_permissions=True)
                    frappe.db.commit()
                    return ("whatsapp", mobile)
            except Exception:
                frappe.log_error(
                    frappe.get_traceback(), "SPM OTP WhatsApp delivery failed"
                )

    frappe.sendmail(
        recipients=[usr],
        subject=f"{APP_NAME} Password Reset Code",
        message=message,
        now=True,
    )
    return ("email", usr)
