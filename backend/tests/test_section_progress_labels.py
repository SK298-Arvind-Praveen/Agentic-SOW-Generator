import pytest

from app.core.nodes import _section_progress_label


@pytest.mark.parametrize('title, expected', [
    ('2. About Shellkode', 'About Shellkode'),
    ('2.1. Solution Architecture', 'Solution Architecture'),
    ('3) Scope of Work', 'Scope of Work'),
    ('4 - Assumptions', 'Assumptions'),
    ('About Shellkode', 'About Shellkode'),
    ('24/7 Support', '24/7 Support'),
])
def test_section_progress_label(title, expected):
    assert _section_progress_label(title) == expected
