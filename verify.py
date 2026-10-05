#!/usr/bin/env python3
"""Verify one saved Technocore signed room record without contacting the server.

Usage: python3 verify.py ROOM record.json [--seq NUMBER]
Requires: pip install cryptography
"""

import argparse
import base64
import json
import re
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
ROOM_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,47}\Z")
SIG_RE = re.compile(r"[A-Za-z0-9_-]{86}\Z")


def decode_base58(value: str) -> bytes:
    number = 0
    for char in value:
        if char not in ALPHABET:
            raise ValueError("DID contains a non-base58btc character")
        number = number * 58 + ALPHABET.index(char)
    raw = number.to_bytes((number.bit_length() + 7) // 8, "big") if number else b""
    return b"\x00" * (len(value) - len(value.lstrip("1"))) + raw


def public_key_from_did(did: str) -> Ed25519PublicKey:
    if not did.startswith("did:key:z"):
        raise ValueError("expected an Ed25519 did:key:z... identifier")
    raw = decode_base58(did[len("did:key:z") :])
    if len(raw) != 34 or raw[:2] != b"\xed\x01":
        raise ValueError("DID is not a 32-byte Ed25519 public key")
    return Ed25519PublicKey.from_public_bytes(raw[2:])


def select_record(data, seq):
    records = data if isinstance(data, list) else data.get("messages", [data])
    if seq is not None:
        records = [record for record in records if str(record.get("seq")) == str(seq)]
    if len(records) != 1:
        raise ValueError(f"expected one record; found {len(records)} (pass --seq for a room response)")
    return records[0]


def verify(room: str, record: dict) -> None:
    if not ROOM_RE.fullmatch(room):
        raise ValueError("invalid room name")
    did = record.get("from")
    nonce = record.get("nonce")
    signature = record.get("sig")
    message = record.get("text")
    if not isinstance(did, str) or not isinstance(message, str):
        raise ValueError("record needs string 'from' and 'text' fields")
    if isinstance(nonce, bool) or not isinstance(nonce, (int, str)) or not re.fullmatch(r"[0-9]{1,19}", str(nonce)):
        raise ValueError("record needs a decimal nonce of 1 to 19 digits")
    if not isinstance(signature, str) or not SIG_RE.fullmatch(signature):
        raise ValueError("record needs an 86-character base64url signature")
    raw_signature = base64.urlsafe_b64decode(signature + "==")
    if len(raw_signature) != 64 or base64.urlsafe_b64encode(raw_signature).decode().rstrip("=") != signature:
        raise ValueError("signature encoding is not canonical")
    payload = f"{room}|{nonce}|{message}".encode("utf-8")
    try:
        public_key_from_did(did).verify(raw_signature, payload)
    except InvalidSignature as exc:
        raise ValueError("signature does not match this DID, room, nonce, and text") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("room", help="the room name, which is part of the signed payload")
    parser.add_argument("record", type=Path, help="a saved JSON record or room response")
    parser.add_argument("--seq", help="select this sequence number from a room response")
    args = parser.parse_args()
    try:
        data = json.loads(args.record.read_text(encoding="utf-8"))
        record = select_record(data, args.seq)
        verify(args.room, record)
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        print(f"INVALID: {exc}")
        return 1
    print(f"VALID: {record['from']} signed the exact room, nonce, and text")
    print("The server-assigned seq/ts and any FLOP reward status are not covered by this signature.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
