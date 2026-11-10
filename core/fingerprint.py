"""Sidik jari lewat WebAuthn: memakai sidik jari yang sudah tersimpan di laptop (Windows Hello / Touch ID).

Browser meminta OS memverifikasi pengguna (user verification) dan menandatangani tantangan dari server.
Server hanya menyimpan kunci publik; template sidik jari tidak pernah keluar dari laptop.
"""
import json

from webauthn import (generate_authentication_options, generate_registration_options, options_to_json,
                      verify_authentication_response, verify_registration_response)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.structs import (AuthenticatorAttachment, AuthenticatorSelectionCriteria,
                                      PublicKeyCredentialDescriptor, ResidentKeyRequirement,
                                      UserVerificationRequirement)

RP_NAME = "BoiKript"


def begin_register(rp_id: str, username: str) -> dict:
    opts = generate_registration_options(
        rp_id=rp_id, rp_name=RP_NAME, user_name=username, user_id=username.encode("utf-8"),
        authenticator_selection=AuthenticatorSelectionCriteria(
            authenticator_attachment=AuthenticatorAttachment.PLATFORM,       # pembaca bawaan laptop
            resident_key=ResidentKeyRequirement.DISCOURAGED,
            user_verification=UserVerificationRequirement.REQUIRED))         # wajib verifikasi biometrik/PIN
    return {"options": json.loads(options_to_json(opts)), "challenge": bytes_to_base64url(opts.challenge)}


def finish_register(credential: dict, challenge: str, rp_id: str, origin: str) -> dict:
    v = verify_registration_response(
        credential=credential, expected_challenge=base64url_to_bytes(challenge),
        expected_rp_id=rp_id, expected_origin=origin, require_user_verification=True)
    return {"id": bytes_to_base64url(v.credential_id), "pk": bytes_to_base64url(v.credential_public_key),
            "count": v.sign_count}


def begin_auth(rp_id: str, record: dict) -> dict:
    opts = generate_authentication_options(
        rp_id=rp_id, user_verification=UserVerificationRequirement.REQUIRED,
        allow_credentials=[PublicKeyCredentialDescriptor(id=base64url_to_bytes(record["id"]))])
    return {"options": json.loads(options_to_json(opts)), "challenge": bytes_to_base64url(opts.challenge)}


def finish_auth(credential: dict, challenge: str, rp_id: str, origin: str, record: dict) -> dict:
    v = verify_authentication_response(
        credential=credential, expected_challenge=base64url_to_bytes(challenge),
        expected_rp_id=rp_id, expected_origin=origin,
        credential_public_key=base64url_to_bytes(record["pk"]),
        credential_current_sign_count=record["count"], require_user_verification=True)
    return {**record, "count": v.new_sign_count}