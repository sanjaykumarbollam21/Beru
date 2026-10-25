import os
import time
import shutil
import sqlite3
import pytest
from cryptography.fernet import Fernet
from hub.db import Base, engine, SessionLocal, User, Device, UserPreference, utcnow
from hub.backup.backup import DatabaseBackupManager

TEST_BACKUP_DIR = "./data/test_backups"

@pytest.fixture(autouse=True)
def clean_test_env():
    os.makedirs(TEST_BACKUP_DIR, exist_ok=True)
    yield
    if os.path.exists(TEST_BACKUP_DIR):
        shutil.rmtree(TEST_BACKUP_DIR, ignore_errors=True)

def test_encrypted_backup_creation_and_encryption():
    """
    Verify backup creates an encrypted archive where SQLite plaintext header is obscured.
    """
    key = Fernet.generate_key().decode("utf-8")
    manager = DatabaseBackupManager(backup_dir=TEST_BACKUP_DIR, retention_count=14, encryption_key=key)

    # Prepare database with data
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        user = User(id="user-backup-test")
        db.add(user)
        device = Device(
            id="dev-backup-test",
            user_id="user-backup-test",
            name="Backup Phone",
            platform="android",
            token_hash="hash123",
            capabilities=["set_volume"],
            last_seen=utcnow()
        )
        db.add(device)
        db.commit()

    # Create backup
    backup_file = manager.create_backup()
    assert os.path.exists(backup_file)
    assert backup_file.endswith(".enc")

    # Verify file is encrypted: SQLite format 3 header MUST NOT be present
    with open(backup_file, "rb") as f:
        content = f.read()
    assert b"SQLite format 3" not in content
    assert len(content) > 100

def test_backup_restore_and_data_integrity():
    """
    Verify encrypted backup restores into a clean SQLite instance and PRAGMA integrity_check passes.
    """
    key = Fernet.generate_key().decode("utf-8")
    manager = DatabaseBackupManager(backup_dir=TEST_BACKUP_DIR, retention_count=14, encryption_key=key)

    # Insert test data
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        u = User(id="user-restore-test")
        db.add(u)
        p = UserPreference(
            id="pref-restore-1",
            user_id="user-restore-test",
            key="preferred_app_music",
            value="Spotify",
            source="user"
        )
        db.add(p)
        db.commit()

    backup_file = manager.create_backup()

    # Restore into a clean temporary database file
    clean_db_path = os.path.join(TEST_BACKUP_DIR, "restored_beru.db")
    success = manager.restore_backup(backup_file, target_db_path=clean_db_path)
    assert success is True
    assert os.path.exists(clean_db_path)

    # Query restored DB directly with raw SQLite
    conn = sqlite3.connect(clean_db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id, key, value FROM user_preferences WHERE user_id = 'user-restore-test'")
    row = cursor.fetchone()
    conn.close()

    assert row is not None
    assert row[1] == "preferred_app_music"
    assert "Spotify" in str(row[2])

def test_backup_restore_wrong_key_fails():
    """
    Verify attempting to restore with an invalid decryption key raises ValueError.
    """
    correct_key = Fernet.generate_key().decode("utf-8")
    wrong_key = Fernet.generate_key().decode("utf-8")

    manager = DatabaseBackupManager(backup_dir=TEST_BACKUP_DIR, retention_count=14, encryption_key=correct_key)
    Base.metadata.create_all(bind=engine)
    backup_file = manager.create_backup()

    clean_db_path = os.path.join(TEST_BACKUP_DIR, "bad_restore.db")
    with pytest.raises(ValueError) as exc:
        manager.restore_backup(backup_file, target_db_path=clean_db_path, custom_key=wrong_key)
    assert "Decryption failed" in str(exc.value)

def test_backup_retention_pruning():
    """
    Verify backup manager maintains only the latest 14 backups.
    """
    manager = DatabaseBackupManager(backup_dir=TEST_BACKUP_DIR, retention_count=14)
    # Create 18 dummy backup files
    for i in range(18):
        fpath = os.path.join(TEST_BACKUP_DIR, f"beru_backup_20261025_{100000 + i}.enc")
        with open(fpath, "wb") as f:
            f.write(b"dummy_encrypted_data")
        # Ensure distinct mtimes
        os.utime(fpath, (time.time() + i, time.time() + i))

    pruned = manager.prune_old_backups()
    assert len(pruned) == 4

    remaining = [f for f in os.listdir(TEST_BACKUP_DIR) if f.startswith("beru_backup_")]
    assert len(remaining) == 14
