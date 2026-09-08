"""Check privileged file metadata using the real rootfs copy script."""

import os
import stat
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TEST_UID = 1701
TEST_GID = 1702
SETUID_SETGID_MODE = 0o6751


def capability_attribute():
    # Linux vfs_cap_data revision 2: flags, then permitted/inheritable masks
    # for capability bits 0-31 and 32-63. No libcap tools are needed in the image.
    revision_2 = 0x02000000
    effective_flag = 0x00000001
    net_bind_service = 1 << 10
    return struct.pack(
        "<IIIII",
        revision_2 | effective_flag,
        net_bind_service,
        0,  # Inheritable low bits.
        0,  # Permitted high bits.
        0,  # Inheritable high bits.
    )


def acl_attribute():
    # Linux POSIX ACL xattr: version header, then (tag, permissions, ID).
    # Represent: user::rw-, user:1701:r--, group::---, mask::r--, other::---.
    version = 2
    owner_tag = 0x01
    named_user_tag = 0x02
    group_tag = 0x04
    mask_tag = 0x10
    other_tag = 0x20
    no_id = 0xFFFFFFFF
    read = 0x04
    write = 0x02
    entries = [
        (owner_tag, read | write, no_id),
        (named_user_tag, read, TEST_UID),
        (group_tag, 0, no_id),
        (mask_tag, read, no_id),
        (other_tag, 0, no_id),
    ]
    attribute = struct.pack("<I", version)
    for tag, permissions, user_id in entries:
        attribute += struct.pack("<HHI", tag, permissions, user_id)
    return attribute


class CopyMetadataTests(unittest.TestCase):
    def test_copy_preserves_privileged_metadata(self):
        with tempfile.TemporaryDirectory(prefix="101strap-copy-test-") as directory:
            source = Path(directory) / "source"
            target = Path(directory) / "target"
            (source / "etc").mkdir(parents=True)
            target.mkdir()

            owned_file = source / "etc/owned"
            owned_file.write_text("owned data")
            os.chown(owned_file, TEST_UID, TEST_GID)
            # chown can clear setuid/setgid, so apply the mode afterwards.
            owned_file.chmod(SETUID_SETGID_MODE)

            capability_file = source / "etc/capability"
            capability_file.write_text("capability data")
            capability_file.chmod(0o755)
            os.setxattr(capability_file, "security.capability", capability_attribute())

            acl_file = source / "etc/acl"
            acl_file.write_text("ACL data")
            os.setxattr(acl_file, "system.posix_acl_access", acl_attribute())

            subprocess.run(
                ["bash", str(REPO / "rootfs/copy.sh"), str(source), str(target)],
                check=True,
            )

            copied_file = target / "etc/owned"
            copied_stat = copied_file.stat()
            self.assertEqual(copied_stat.st_uid, TEST_UID, "copied owner UID")
            self.assertEqual(copied_stat.st_gid, TEST_GID, "copied owner GID")
            self.assertEqual(
                stat.S_IMODE(copied_stat.st_mode),
                SETUID_SETGID_MODE,
                "copied permissions, including setuid/setgid",
            )
            for filename, attribute in (
                ("capability", "security.capability"),
                ("acl", "system.posix_acl_access"),
            ):
                with self.subTest(file=filename, attribute=attribute):
                    # A user namespace may translate capability xattrs. Compare
                    # the kernel's stored source value with the copied value.
                    expected = os.getxattr(source / "etc" / filename, attribute)
                    actual = os.getxattr(target / "etc" / filename, attribute)
                    self.assertEqual(actual, expected)


if __name__ == "__main__":
    if not (Path("/run/.containerenv").exists() or Path("/.dockerenv").exists()):
        raise SystemExit(
            "Run this test in a disposable container with the repo at /srv."
        )
    if os.geteuid() != 0:
        raise SystemExit("Run this test as root inside the disposable container.")
    unittest.main(verbosity=2)
