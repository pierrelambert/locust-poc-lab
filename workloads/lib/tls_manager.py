"""TLS/SNI certificate manager for Redis connections.

Provides SSL context creation, certificate validation, and certificate
loading from files, environment variables, and Kubernetes secrets.

The ``cryptography`` package is **optional** — certificate inspection
features degrade gracefully when it is not installed.  Basic SSL context
creation relies only on the stdlib :mod:`ssl` module.
"""

import base64
import json
import logging
import os
import ssl
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Optional dependency --------------------------------------------------
try:
    from cryptography import x509
    from cryptography.hazmat.backends import default_backend

    _HAS_CRYPTOGRAPHY = True
except ImportError:  # pragma: no cover
    _HAS_CRYPTOGRAPHY = False


class TLSCertificateManager:
    """Manage TLS certificates for Redis connections.

    Supports loading certs from local files, environment variables, and
    Kubernetes secrets.  When the *cryptography* package is available,
    certificate validation and metadata extraction are also supported.
    """

    def __init__(
        self,
        cert_path: Optional[str] = None,
        key_path: Optional[str] = None,
        ca_path: Optional[str] = None,
        sni_hostname: Optional[str] = None,
    ) -> None:
        self.cert_path = cert_path
        self.key_path = key_path
        self.ca_path = ca_path
        self.sni_hostname = sni_hostname

    # ------------------------------------------------------------------
    # SSL context
    # ------------------------------------------------------------------

    def create_ssl_context(
        self,
        verify_mode: ssl.VerifyMode = ssl.CERT_REQUIRED,
        check_hostname: bool = True,
    ) -> ssl.SSLContext:
        """Build an :class:`ssl.SSLContext` from configured cert paths.

        Uses only stdlib :mod:`ssl` — no third-party dependencies.
        """
        ctx = ssl.create_default_context()
        ctx.check_hostname = check_hostname
        ctx.verify_mode = verify_mode

        if self.ca_path:
            if not Path(self.ca_path).exists():
                raise FileNotFoundError(f"CA certificate not found: {self.ca_path}")
            ctx.load_verify_locations(cafile=self.ca_path)
            logger.info("Loaded CA certificate from %s", self.ca_path)

        if self.cert_path and self.key_path:
            if not Path(self.cert_path).exists():
                raise FileNotFoundError(f"Client certificate not found: {self.cert_path}")
            if not Path(self.key_path).exists():
                raise FileNotFoundError(f"Client key not found: {self.key_path}")
            ctx.load_cert_chain(certfile=self.cert_path, keyfile=self.key_path)
            logger.info("Loaded client certificate from %s", self.cert_path)

        return ctx

    # ------------------------------------------------------------------
    # Certificate inspection  (requires cryptography)
    # ------------------------------------------------------------------

    def validate_certificate(self, cert_path: Optional[str] = None) -> Tuple[bool, str]:
        """Check certificate validity and expiry.

        Returns ``(is_valid, message)``."""
        if not _HAS_CRYPTOGRAPHY:
            return False, "cryptography package not installed — cannot validate"

        target = cert_path or self.cert_path
        if not target:
            return False, "No certificate path provided"
        if not Path(target).exists():
            return False, f"Certificate file not found: {target}"

        try:
            with open(target, "rb") as fh:
                cert = x509.load_pem_x509_certificate(fh.read(), default_backend())

            now = datetime.utcnow()
            if now < cert.not_valid_before_utc.replace(tzinfo=None):
                return False, f"Certificate not yet valid (from {cert.not_valid_before_utc})"
            if now > cert.not_valid_after_utc.replace(tzinfo=None):
                return False, f"Certificate expired on {cert.not_valid_after_utc}"

            days_left = (cert.not_valid_after_utc.replace(tzinfo=None) - now).days
            subject = cert.subject.rfc4514_string()
            issuer = cert.issuer.rfc4514_string()
            return True, (
                f"Certificate valid — Subject: {subject}, Issuer: {issuer}, "
                f"Expires: {cert.not_valid_after_utc} ({days_left} days)"
            )
        except Exception as exc:  # noqa: BLE001
            return False, f"Validation failed: {exc}"

    def get_certificate_info(self, cert_path: Optional[str] = None) -> Dict[str, Any]:
        """Return certificate metadata as a dict.

        Returns an empty dict when *cryptography* is not installed."""
        if not _HAS_CRYPTOGRAPHY:
            logger.warning("cryptography not installed — cert info unavailable")
            return {}

        target = cert_path or self.cert_path
        if not target or not Path(target).exists():
            return {}

        try:
            with open(target, "rb") as fh:
                cert = x509.load_pem_x509_certificate(fh.read(), default_backend())
            return {
                "subject": cert.subject.rfc4514_string(),
                "issuer": cert.issuer.rfc4514_string(),
                "serial_number": cert.serial_number,
                "not_valid_before": cert.not_valid_before_utc.isoformat(),
                "not_valid_after": cert.not_valid_after_utc.isoformat(),
                "version": cert.version.name,
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to read certificate info: %s", exc)
            return {}

    # ------------------------------------------------------------------
    # Loaders
    # ------------------------------------------------------------------

    @classmethod
    def load_from_environment(cls) -> "TLSCertificateManager":
        """Create a manager from ``REDIS_TLS_*`` environment variables.

        Reads ``REDIS_TLS_CERT``, ``REDIS_TLS_KEY``, ``REDIS_TLS_CA``,
        and optionally ``REDIS_TLS_SNI``.
        """
        return cls(
            cert_path=os.environ.get("REDIS_TLS_CERT"),
            key_path=os.environ.get("REDIS_TLS_KEY"),
            ca_path=os.environ.get("REDIS_TLS_CA"),
            sni_hostname=os.environ.get("REDIS_TLS_SNI"),
        )

    @classmethod
    def load_from_kubernetes_secret(
        cls,
        secret_name: str,
        namespace: str = "default",
        cert_key: str = "tls.crt",
        key_key: str = "tls.key",
        ca_key: str = "ca.crt",
        output_dir: str = "/tmp/redis-certs",
    ) -> "TLSCertificateManager":
        """Extract certificates from a Kubernetes TLS secret via ``kubectl``.

        The decoded PEM files are written to *output_dir* and a new
        :class:`TLSCertificateManager` is returned pointing at them.
        """
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        result = subprocess.run(
            ["kubectl", "get", "secret", secret_name, "-n", namespace, "-o", "json"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(f"kubectl failed: {result.stderr.strip()}")

        data = json.loads(result.stdout).get("data", {})

        paths: Dict[str, Optional[str]] = {"cert": None, "key": None, "ca": None}

        for label, k, fname, mode in [
            ("cert", cert_key, "tls.crt", 0o644),
            ("key", key_key, "tls.key", 0o600),
            ("ca", ca_key, "ca.crt", 0o644),
        ]:
            if k in data:
                out = os.path.join(output_dir, fname)
                with open(out, "wb") as fh:
                    fh.write(base64.b64decode(data[k]))
                os.chmod(out, mode)
                paths[label] = out
                logger.info("Extracted %s to %s", label, out)

        return cls(cert_path=paths["cert"], key_path=paths["key"], ca_path=paths["ca"])

    # ------------------------------------------------------------------
    # Redis kwargs helper
    # ------------------------------------------------------------------

    def ssl_kwargs(self) -> Dict[str, Any]:
        """Return a dict of SSL-related kwargs for ``redis.Redis()``.

        This is the primary integration point used by
        :func:`topology_clients._apply_ssl`.
        """
        kw: Dict[str, Any] = {"ssl": True}

        if self.ca_path:
            kw["ssl_ca_certs"] = self.ca_path
        if self.cert_path:
            kw["ssl_certfile"] = self.cert_path
        if self.key_path:
            kw["ssl_keyfile"] = self.key_path
        if self.sni_hostname:
            kw["ssl_check_hostname"] = True

        kw["ssl_cert_reqs"] = "required"
        return kw


