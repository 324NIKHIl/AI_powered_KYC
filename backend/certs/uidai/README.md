# UIDAI public-key certificates

Put UIDAI's **Aadhaar Secure QR / offline e-KYC public-key certificate(s)** in this
folder (`.cer`, `.crt`, `.pem` or `.der`, DER or PEM encoded). The backend uses
them to verify the RSA-SHA256 signature inside every Aadhaar Secure QR code.

- Download them from UIDAI's official website (uidai.gov.in → Ecosystem →
  Aadhaar Secure QR Code / Offline e-KYC; the file is named like
  `uidai_offline_publickey_<date>.cer`).
- UIDAI has rotated this key over the years — add every certificate you can find.
  Each QR is checked against all of them.
- Certificates are public, so committing them is fine.

Without a certificate here, QR data is still decoded and cross-checked against
the card, but its signature status is reported as `unverified`.

The folder can be changed with the `UIDAI_CERT_DIR` environment variable.

You can also point `AADHAAR_CERTIFICATE_PATH` at a single certificate file. Staging/test certificates are
ignored on purpose: they cannot verify real cards and would wrongly flag genuine ones. A QR whose signature
cannot be checked is reported as *unverified* → the document status is `VERIFICATION_UNAVAILABLE`, not valid.
