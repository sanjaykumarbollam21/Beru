import os
import shutil
import hashlib
import logging
from typing import Dict, Optional, Generator, Tuple
from cryptography.fernet import Fernet
from hub.config import settings
from hub.transfer.models import TransferRecord, utcnow

logger = logging.getLogger(__name__)

class TransferStore:
    def __init__(self, storage_dir: Optional[str] = None):
        self.storage_dir = storage_dir or settings.TRANSFER_STORAGE_DIR
        os.makedirs(self.storage_dir, exist_ok=True)

        # In-memory transfer records
        self._records: Dict[str, TransferRecord] = {}

        # Encryption at rest
        if settings.TRANSFER_ENCRYPTION_KEY:
            try:
                self.cipher = Fernet(settings.TRANSFER_ENCRYPTION_KEY.encode())
            except Exception:
                self.cipher = Fernet(Fernet.generate_key())
        else:
            self.cipher = Fernet(Fernet.generate_key())

    def add_record(self, record: TransferRecord):
        self._records[record.transfer_id] = record
        transfer_path = self._get_transfer_dir(record.transfer_id)
        os.makedirs(transfer_path, exist_ok=True)

    def get_record(self, transfer_id: str) -> Optional[TransferRecord]:
        rec = self._records.get(transfer_id)
        if rec and rec.is_expired():
            rec.status = "expired"
        return rec

    def list_pending_for_device(self, user_id: str, device_id: str) -> list[TransferRecord]:
        return [
            r for r in self._records.values()
            if r.user_id == user_id
            and (r.to_device_id == device_id or r.to_device_id.lower() in ("windows", "android"))
            and r.status == "ready"
            and not r.is_expired()
        ]

    def _get_transfer_dir(self, transfer_id: str) -> str:
        return os.path.join(self.storage_dir, transfer_id)

    def save_chunk(self, transfer_id: str, chunk_index: int, raw_bytes: bytes) -> int:
        record = self.get_record(transfer_id)
        if not record:
            raise KeyError("Transfer not found")

        # Encrypt chunk at rest
        encrypted = self.cipher.encrypt(raw_bytes)
        chunk_file = os.path.join(self._get_transfer_dir(transfer_id), f"chunk_{chunk_index}.enc")
        with open(chunk_file, "wb") as f:
            f.write(encrypted)

        record.received_chunks.add(chunk_index)
        record.status = "uploading"
        return len(record.received_chunks)

    def assemble_and_verify(self, record: TransferRecord) -> Tuple[bool, str]:
        transfer_dir = self._get_transfer_dir(record.transfer_id)
        hasher = hashlib.sha256()
        total_size = 0

        for i in range(record.total_chunks):
            chunk_file = os.path.join(transfer_dir, f"chunk_{i}.enc")
            if not os.path.exists(chunk_file):
                return False, f"Missing chunk {i}"

            with open(chunk_file, "rb") as f:
                enc = f.read()
            dec = self.cipher.decrypt(enc)
            hasher.update(dec)
            total_size += len(dec)

        calc_hash = hasher.hexdigest().lower()
        if calc_hash != record.sha256.lower():
            logger.warning(f"Hash mismatch for {record.transfer_id}: expected {record.sha256}, got {calc_hash}")
            self.delete_transfer_data(record.transfer_id)
            record.status = "failed"
            return False, "Hash mismatch: corrupt or tampered transfer"

        if total_size != record.file_size:
            logger.warning(f"Size mismatch for {record.transfer_id}: expected {record.file_size}, got {total_size}")
            self.delete_transfer_data(record.transfer_id)
            record.status = "failed"
            return False, "Size mismatch"

        record.status = "ready"
        return True, "verified"

    def get_decrypted_stream(
        self,
        record: TransferRecord,
        start_byte: int = 0,
        length: Optional[int] = None
    ) -> Generator[bytes, None, None]:
        transfer_dir = self._get_transfer_dir(record.transfer_id)
        current_offset = 0
        end_byte = (start_byte + length) if length is not None else record.file_size

        for i in range(record.total_chunks):
            chunk_file = os.path.join(transfer_dir, f"chunk_{i}.enc")
            if not os.path.exists(chunk_file):
                break

            with open(chunk_file, "rb") as f:
                dec = self.cipher.decrypt(f.read())

            chunk_len = len(dec)
            chunk_start = current_offset
            chunk_end = current_offset + chunk_len
            current_offset += chunk_len

            # Check if this chunk overlaps [start_byte, end_byte)
            if chunk_end <= start_byte:
                continue
            if chunk_start >= end_byte:
                break

            slice_start = max(0, start_byte - chunk_start)
            slice_end = min(chunk_len, end_byte - chunk_start)
            yield dec[slice_start:slice_end]

    def delete_transfer_data(self, transfer_id: str):
        transfer_dir = self._get_transfer_dir(transfer_id)
        if os.path.exists(transfer_dir):
            shutil.rmtree(transfer_dir, ignore_errors=True)

    def sweep_expired(self) -> int:
        swept = 0
        now = utcnow()
        for t_id, record in list(self._records.items()):
            if record.expires_at < now or record.status in ("delivered", "failed", "expired"):
                self.delete_transfer_data(t_id)
                if record.status not in ("delivered", "failed"):
                    record.status = "expired"
                swept += 1
        return swept

transfer_store = TransferStore()
