def parse_balance(balances):
    return {b["currency"]: {"available": b["available"], "balance": b["balance"]} for b in balances}


def instrument_counter_currency(instrument):
    return instrument.split("-")[1]


def instrument_base_currency(instrument):
    return instrument.split("-")[0]
