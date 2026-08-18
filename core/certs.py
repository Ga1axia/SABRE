"""Create a local CA plus gate and agent client certs for I1 mTLS."""

from __future__ import annotations

import ipaddress
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from core.paths import Paths


def _key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _name(cn: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])


def _dump_key(key: rsa.RSAPrivateKey, path: Path) -> None:
    path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )


def _dump_cert(cert: x509.Certificate, path: Path) -> None:
    path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


def _cert(subject, issuer, pub, issuer_key, ca: bool, san_ip: str | None = None) -> x509.Certificate:
    now = datetime.now(UTC)
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(pub)
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=ca, path_length=None if not ca else 0), critical=True)
    )
    if san_ip:
        builder = builder.add_extension(
            x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address(san_ip))]),
            critical=False,
        )
    return builder.sign(issuer_key, hashes.SHA256())


def generate_mtls(paths: Paths) -> None:
    paths.certs.mkdir(parents=True, exist_ok=True)
    ca_key_p = paths.certs / "ca.key"
    ca_crt_p = paths.certs / "ca.crt"
    if ca_crt_p.exists() and (paths.certs / "gate.crt").exists() and (paths.certs / "agent.crt").exists():
        return
    ca_key = _key()
    ca_cert = _cert(_name("sabre-ca"), _name("sabre-ca"), ca_key.public_key(), ca_key, ca=True)
    _dump_key(ca_key, ca_key_p)
    _dump_cert(ca_cert, ca_crt_p)

    gate_key = _key()
    gate_cert = _cert(_name("sabre-gate"), ca_cert.subject, gate_key.public_key(), ca_key, False, "127.0.0.1")
    _dump_key(gate_key, paths.certs / "gate.key")
    _dump_cert(gate_cert, paths.certs / "gate.crt")

    agent_key = _key()
    agent_cert = _cert(_name("sabre-agent"), ca_cert.subject, agent_key.public_key(), ca_key, False)
    _dump_key(agent_key, paths.certs / "agent.key")
    _dump_cert(agent_cert, paths.certs / "agent.crt")


def certs_present(paths: Paths) -> bool:
    needed = ["ca.crt", "gate.crt", "gate.key", "agent.crt", "agent.key"]
    return all((paths.certs / n).exists() for n in needed)
