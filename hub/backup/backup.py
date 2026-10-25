import os
import time
import glob
import sqlite3
import logging
from datetime import datetime, timezone
from typing import Optional, List
from cryptography.fernet import Fernet
from hub.config import settings

logger = logging.getLogger(__name__)

class DatabaseBackupManager:
    """
    Handles encrypted SQLite database backups and restores with retention policies.
    """
    def __init__(
        self,
        backup_dir: str = settings.BACKUP_DIR,
        retention_count: int = settings.BACKUP_RETENTION_COUNT,
        encryption_key: Optional[str] = None
    ):
        self.backup_dir = backup_dir
        self.retention_count = retention_count
        # Default or configured Fernet encryption key
        if encryption_key:
            self.key = encryption_key.encode("utf-8")
        elif settings.BACKUP_ENCRYPTION_KEY:
            self.key = settings.BACKUP_ENCRYPTION_KEY.encode("utf-8")
        else:
            # Generate deterministic fallback key based on app name or generate valid Fernet key
            self.key = Fernet.generate_key()

    def get_fernet(self, custom_key: Optional[str] = None) -> Fernet:
        k = custom_key.encode("utf-8") if custom_key else self.key
        return Fernet(k)

    def create_backup(
        self,
        source_db_path: Optional[str] = None,
        custom_key: Optional[str] = None
    ) -> str:
        """
        Creates an encrypted, consistent snapshot of the SQLite database.
        Prunes old backups to respect retention policy.
        """
        db_path = source_db_path or settings.DATABASE_URL.replace("sqlite:///", "")
        if not os.path.exists(db_path):
            raise FileNotFoundError(f"Database file not found at: {db_path}")

        os.makedirs(self.backup_dir, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_filename = f"beru_backup_{ts}.enc"
        backup_path = os.path.join(self.backup_dir, backup_filename)

        # 1. Create consistent in-memory/temp copy using sqlite3 backup API
        temp_snapshot = backup_path + ".tmp"
        try:
            src_conn = sqlite3.connect(db_path)
            dst_conn = sqlite3.connect(temp_snapshot)
            with dst_conn:
                src_conn.backup(dst_conn)
            dst_conn.close()
            src_conn.close()

            # 2. Read snapshot bytes and encrypt
            with open(temp_snapshot, "rb") as f:
                raw_bytes = f.read()

            fernet = self.get_fernet(custom_key)
            encrypted_data = fernet.encrypt(raw_bytes)

            with open(backup_path, "wb") as f:
                f.write(encrypted_data)

            logger.info(f"Created encrypted database backup at {backup_path} ({len(encrypted_data)} bytes)")
        finally:
            if os.path.exists(temp_snapshot):
                try:
                    os.remove(temp_snapshot)
                except Exception:
                    pass

        # 3. Enforce retention policy
        self.prune_old_backups()
        return backup_path

    def restore_backup(
        self,
        backup_path: str,
        target_db_path: Optional[str] = None,
        custom_key: Optional[str] = None
    ) -> bool:
        """
        Decrypts a backup file and restores it to target_db_path.
        Verifies SQLite PRAGMA integrity_check before finalizing.
        """
        if not os.path.exists(backup_path):
            raise FileNotFoundError(f"Backup file not found at: {backup_path}")

        target_path = target_db_path or settings.DATABASE_URL.replace("sqlite:///", "")
        fernet = self.get_fernet(custom_key)

        with open(backup_path, "rb") as f:
            encrypted_data = f.read()

        try:
            decrypted_data = fernet.decrypt(encrypted_data)
        except Exception as e:
            logger.error(f"Failed to decrypt backup {backup_path}: {e}")
            raise ValueError("Decryption failed: invalid encryption key or corrupted backup") from e

        temp_restore = target_path + ".restore_tmp"
        try:
            with open(temp_restore, "wb") as f:
                f.write(decrypted_data)

            # Integrity check
            conn = sqlite3.connect(temp_restore)
            cursor = conn.cursor()
            cursor.execute("PRAGMA integrity_check;")
            row = cursor.fetchone()
            conn.close()

            if not row or row[0] != "ok":
                raise ValueError(f"Restored database failed integrity check: {row}")

            # Overwrite target safely
            if os.path.exists(target_path):
                os.replace(temp_restore, target_path)
            else:
                os.rename(temp_restore, target_path)

            logger.info(f"Successfully restored and verified database to {target_path}")
            return True
        finally:
            if os.path.exists(temp_restore):
                try:
                    os.remove(temp_restore)
                except Exception:
                    pass

    def prune_old_backups(self) -> List[str]:
        """
        Keeps only the most recent `retention_count` backups, deleting older ones.
        """
        if not os.path.exists(self.backup_dir):
            return []

        files = glob.glob(os.path.join(self.backup_dir, "beru_backup_*.enc"))
        # Sort oldest to newest by modification time
        files.sort(key=os.path.getmtime)

        deleted = []
        excess = len(files) - self.retention_count
        if excess > 0:
            to_delete = files[:excess]
            for f in to_delete:
                try:
                    os.remove(f)
                    deleted.append(f)
                    logger.info(f"Pruned old backup: {f}")
                except Exception as e:
                    logger.warning(f"Failed to prune backup {f}: {e}")
        return deleted

backup_manager = DatabaseBackupManager()
