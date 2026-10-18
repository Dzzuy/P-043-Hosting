"""Operational denominators must retain recovered errors and unknown measurements."""
from eval.copilot_eval.operations import operations


def test_attempt_failure_is_retained_when_request_recovers_or_falls_back():
    rows=[
        {'status':'answered','trace':[{'llm':True,'error_type':'TimeoutError','failure_kind':'provider'}]},
        {'status':'abstained','reason_code':'verification_failed','trace':[{'llm':True,'error_type':'ContractError','failure_kind':'output_contract'}]},
        {'error_type':'ConnectionError','trace':[{'llm':True,'error_type':'ConnectionError','failure_kind':'provider'}]},
    ]
    result=operations(rows)
    assert result['request_error_rate']=={'numerator':1,'denominator':3,'value':1/3}
    assert result['provider_error_attempt_rate']['numerator']==2
    assert result['schema_contract_error_attempt_rate']['numerator']==1
    assert result['completed_useful_response_after_attempt_error']['numerator']==1
    assert result['completed_useful_response_after_attempt_error']['denominator']==3
    assert result['technical_fallback_rate']['numerator']==1


def test_absent_telemetry_is_unknown_rather_than_zero():
    result=operations([{'http_status':200,'response':{'status':'answered'}}])
    assert result['peak_rss_bytes'] is None
    assert result['provider_retries'] is None
    assert result['llm_timeout_attempt_rate']['value'] is None
    assert result['cost_usd']['agent_actual'] is None
    assert result['cost_usd']['jev_known_positive_cost'] is None
