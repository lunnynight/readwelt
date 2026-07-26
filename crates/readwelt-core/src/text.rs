use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use unicode_normalization::UnicodeNormalization;

/// A paragraph and its half-open offsets into [`PreparedText::text`].
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
pub struct Paragraph {
    pub anchor_id: String,
    pub ordinal: usize,
    pub start_byte: usize,
    pub end_byte: usize,
    pub start_char: usize,
    pub end_char: usize,
    pub text: String,
}

/// Canonical text plus stable paragraph anchors.
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
pub struct PreparedText {
    pub text: String,
    pub digest: String,
    pub paragraphs: Vec<Paragraph>,
}

/// Normalize text, calculate its SHA-256 digest, and create stable paragraphs.
///
/// Normalization removes an initial BOM, converts line endings to LF, applies
/// Unicode NFC, removes horizontal whitespace at line ends, removes outer
/// blank lines, and represents paragraph breaks as exactly one blank line.
pub fn prepare_text(input: &str) -> PreparedText {
    let text = normalize(input);
    let digest = sha256_hex(text.as_bytes());
    let paragraphs = split_paragraphs(&text, &digest);

    PreparedText {
        text,
        digest,
        paragraphs,
    }
}

fn normalize(input: &str) -> String {
    let without_bom = input.strip_prefix('\u{feff}').unwrap_or(input);
    let line_endings = without_bom.replace("\r\n", "\n").replace('\r', "\n");
    let nfc: String = line_endings.nfc().collect();
    let lines: Vec<&str> = nfc
        .lines()
        .map(|line| line.trim_end_matches([' ', '\t']))
        .collect();

    let first_content = lines.iter().position(|line| !line.trim().is_empty());
    let Some(first_content) = first_content else {
        return String::new();
    };
    let last_content = lines
        .iter()
        .rposition(|line| !line.trim().is_empty())
        .expect("a first content line implies a last content line");

    let mut output = String::new();
    let mut pending_blank = false;

    for line in &lines[first_content..=last_content] {
        if line.trim().is_empty() {
            pending_blank = true;
            continue;
        }

        if !output.is_empty() {
            if pending_blank {
                output.push_str("\n\n");
            } else {
                output.push('\n');
            }
        }
        output.push_str(line);
        pending_blank = false;
    }

    output
}

fn split_paragraphs(text: &str, snapshot_digest: &str) -> Vec<Paragraph> {
    if text.is_empty() {
        return Vec::new();
    }

    let mut paragraphs = Vec::new();
    let mut start_byte = 0;
    let mut start_char = 0;

    for (ordinal, paragraph_text) in text.split("\n\n").enumerate() {
        let end_byte = start_byte + paragraph_text.len();
        let char_count = paragraph_text.chars().count();
        let end_char = start_char + char_count;
        let anchor_id = anchor_id(snapshot_digest, start_byte, end_byte);

        paragraphs.push(Paragraph {
            anchor_id,
            ordinal,
            start_byte,
            end_byte,
            start_char,
            end_char,
            text: paragraph_text.to_owned(),
        });

        start_byte = end_byte + 2;
        start_char = end_char + 2;
    }

    paragraphs
}

fn anchor_id(snapshot_digest: &str, start_byte: usize, end_byte: usize) -> String {
    let input = format!("{snapshot_digest}\0{start_byte}\0{end_byte}");
    format!("sha256:{}", sha256_hex(input.as_bytes()))
}

pub(crate) fn sha256_hex(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn normalizes_utf8_and_creates_byte_and_char_anchors() {
        let prepared = prepare_text("\u{feff}  café  \r\n\r\n\r\n第二段\t\r\n仍在第二段\r\n");

        assert_eq!(prepared.text, "  café\n\n第二段\n仍在第二段");
        assert_eq!(prepared.paragraphs.len(), 2);

        let first = &prepared.paragraphs[0];
        assert_eq!((first.start_byte, first.end_byte), (0, 7));
        assert_eq!((first.start_char, first.end_char), (0, 6));
        assert_eq!(&prepared.text[first.start_byte..first.end_byte], first.text);

        let second = &prepared.paragraphs[1];
        assert_eq!(
            (second.start_byte, second.end_byte),
            (9, prepared.text.len())
        );
        assert_eq!(
            (second.start_char, second.end_char),
            (8, prepared.text.chars().count())
        );
        assert_eq!(
            &prepared.text[second.start_byte..second.end_byte],
            second.text
        );
    }

    #[test]
    fn canonically_composes_unicode_before_hashing() {
        let composed = prepare_text("é");
        let decomposed = prepare_text("e\u{301}");

        assert_eq!(composed, decomposed);
        assert_eq!(
            composed.digest,
            "4a99557e4033c3539de2eb65472017cad5f9557f7a0625a09f1c3f6e2ba69c4c" // pragma: allowlist secret
        );
    }

    #[test]
    fn anchor_ids_are_stable_and_snapshot_specific() {
        let first = prepare_text("one\n\ntwo");
        let replay = prepare_text("one\r\n\r\ntwo");
        let changed = prepare_text("ONE\n\ntwo");

        assert_eq!(first, replay);
        assert_ne!(
            first.paragraphs[1].anchor_id,
            changed.paragraphs[1].anchor_id
        );
    }

    #[test]
    fn blank_input_has_no_paragraphs() {
        let prepared = prepare_text(" \r\n\t\r\n");

        assert!(prepared.text.is_empty());
        assert!(prepared.paragraphs.is_empty());
    }
}
