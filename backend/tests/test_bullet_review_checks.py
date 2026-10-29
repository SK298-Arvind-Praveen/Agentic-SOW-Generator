from app.agents.sow_reviewer_agent import bullet_review_checks, apply_corrections


def test_wordiness_and_crowded_list_checks():
    text = '- ' + 'word ' * 28 + '.\n' + '\n'.join('- Keep a distinct obligation.' for _ in range(6))
    result = bullet_review_checks(text, 'customer_responsibilities')
    assert result['bullet_count'] == 7
    assert result['long_bullets'] == [{'line': 1, 'words': 28}]
    assert result['crowded_blocks'] == {'section': 7}
    assert bullet_review_checks(text, 'about_client') == {}


def test_scope_counts_are_per_module_not_whole_scope():
    text = '\n'.join('#### Module ' + str(i) + '\n' + '\n'.join('- Do the work.' for _ in range(4)) for i in range(3))
    assert bullet_review_checks(text, 'scope_of_work')['crowded_blocks'] == {}


def test_about_client_accepts_two_paragraphs():
    original = {'about': 'Example sells software.\n\nIt operates online.'}
    after = 'Example supplies software.\n\nIt operates online.'
    result = apply_corrections(original, {'corrections': [{'section':'about','after':after}]}, {'about':'about_client'}, {})
    assert result['about'] == after
