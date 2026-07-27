# Historical stage navigation fixtures

These payloads are direct `stage-view-cursor.v1` and `stage-navigation.v1`
artifacts. The cursor digest was produced from the pre-v2 field set only:
snapshot identity, historical text-unit schema, stage, policy/index digests,
text-unit frontier, and visited units. The v2 range and element traversal
fields were never added and then removed.

The fixtures are immutable reader inputs. Compatibility tests decode their
original bytes, verify the original v1 digest, and exercise both historical
resume validation and rejection against the complete Source Plane schema.
