from backend.completion_validation import response_problem


def test_empty_response_is_not_success():
    assert response_problem({'message': {'content': None}})


def test_truncated_response_is_not_executable():
    assert response_problem({'finish_reason': 'length', 'message': {'content': 'Done'}})


def test_invalid_second_call_rejects_whole_response():
    calls = [{'function': {'name': 'run_python', 'arguments': '{"code":"print(1)"}'}},
             {'function': {'name': 'run_python', 'arguments': '{"code":"unfinished'}}]
    assert response_problem({'message': {'tool_calls': calls}})


def test_valid_code_and_answer_are_accepted():
    assert response_problem({'message': {'tool_calls': [
        {'function': {'name': 'run_python', 'arguments': '{"code":"print(1)"}'}}
    ]}}) is None
    assert response_problem({'message': {'content': 'The result is 1.'}}) is None
