"""English section criteria must check actual headings, including long names."""
import pytest
from app.harness.checks.done import check_done_item

@pytest.mark.parametrize(('content', 'status', 'why'), [
    ('', 'fail', 'Missing headings: Project scope, Risks and blockers'),
    ('## Project scope\n\nA paragraph', 'fail', 'Missing headings: Risks and blockers'),
    ('## PROJECT SCOPE\n\nA paragraph\n\n## Risks and blockers\n\nB paragraph', 'pass', 'All 2 sections present'),
    ('Project scope and risks and blockers in body text', 'fail', 'Missing headings: Project scope, Risks and blockers'),
])
def test_english_sections(content, status, why):
    result = check_done_item('Sections: Project scope, Risks and blockers', content)
    assert result['status'] == status
    assert result['why'] == why
