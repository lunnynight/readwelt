use std::{
    fs,
    io::{self, Write},
    path::{Path, PathBuf},
};

use serde::{Deserialize, Serialize};
use tempfile::NamedTempFile;
use thiserror::Error;

use crate::text::sha256_hex;

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
pub struct StoredObject {
    pub digest: String,
    /// Path relative to the object-store root.
    pub relative_path: PathBuf,
    pub size: u64,
    pub created: bool,
}

#[derive(Debug, Error)]
pub enum ObjectStoreError {
    #[error("object store I/O failed at {path}: {source}")]
    Io {
        path: PathBuf,
        #[source]
        source: io::Error,
    },
    #[error("existing object at {path} does not match digest {expected}")]
    CorruptObject { path: PathBuf, expected: String },
}

/// Atomically store immutable bytes under `sha256/ab/cd/<digest>`.
///
/// Repeated writes are idempotent. Existing objects are verified before being
/// returned, so a corrupt file is never silently accepted.
pub fn store_object(
    root: impl AsRef<Path>,
    bytes: &[u8],
) -> Result<StoredObject, ObjectStoreError> {
    let root = root.as_ref();
    let digest = sha256_hex(bytes);
    let relative_path = object_path(&digest);
    let destination = root.join(&relative_path);

    if destination.exists() {
        verify_existing(&destination, &digest)?;
        return Ok(StoredObject {
            digest,
            relative_path,
            size: bytes.len() as u64,
            created: false,
        });
    }

    let parent = destination
        .parent()
        .expect("a content-addressed object always has a parent");
    fs::create_dir_all(parent).map_err(|source| io_error(parent, source))?;

    // The temporary file lives beside the destination, making persistence an
    // atomic rename on supported local filesystems.
    let mut temporary = NamedTempFile::new_in(parent).map_err(|source| io_error(parent, source))?;
    temporary
        .write_all(bytes)
        .map_err(|source| io_error(temporary.path(), source))?;
    temporary
        .as_file()
        .sync_all()
        .map_err(|source| io_error(temporary.path(), source))?;

    let created = match temporary.persist_noclobber(&destination) {
        Ok(_) => true,
        Err(error) if error.error.kind() == io::ErrorKind::AlreadyExists => {
            verify_existing(&destination, &digest)?;
            false
        }
        Err(error) => return Err(io_error(&destination, error.error)),
    };

    Ok(StoredObject {
        digest,
        relative_path,
        size: bytes.len() as u64,
        created,
    })
}

fn object_path(digest: &str) -> PathBuf {
    PathBuf::from("sha256")
        .join(&digest[..2])
        .join(&digest[2..4])
        .join(digest)
}

fn verify_existing(path: &Path, expected: &str) -> Result<(), ObjectStoreError> {
    let bytes = fs::read(path).map_err(|source| io_error(path, source))?;
    if sha256_hex(&bytes) != expected {
        return Err(ObjectStoreError::CorruptObject {
            path: path.to_owned(),
            expected: expected.to_owned(),
        });
    }
    Ok(())
}

fn io_error(path: impl AsRef<Path>, source: io::Error) -> ObjectStoreError {
    ObjectStoreError::Io {
        path: path.as_ref().to_owned(),
        source,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn writes_content_addressed_object_and_reuses_it() {
        let root = tempfile::tempdir().unwrap();

        let first = store_object(root.path(), b"readwelt").unwrap();
        assert!(first.created);
        assert_eq!(first.size, 8);
        assert_eq!(
            first.relative_path,
            PathBuf::from("sha256")
                .join("33")
                .join("c2")
                .join("33c2fb0bda090b18a261ce660d7cbbcb3553c726188c6003deba61f917126daf") // pragma: allowlist secret
        );
        assert_eq!(
            fs::read(root.path().join(&first.relative_path)).unwrap(),
            b"readwelt"
        );

        let replay = store_object(root.path(), b"readwelt").unwrap();
        assert!(!replay.created);
        assert_eq!(first.digest, replay.digest);
        assert_eq!(first.relative_path, replay.relative_path);
    }

    #[test]
    fn refuses_corrupt_existing_object() {
        let root = tempfile::tempdir().unwrap();
        let stored = store_object(root.path(), b"original").unwrap();
        fs::write(root.path().join(&stored.relative_path), b"corrupt").unwrap();

        let error = store_object(root.path(), b"original").unwrap_err();
        assert!(matches!(error, ObjectStoreError::CorruptObject { .. }));
    }
}
