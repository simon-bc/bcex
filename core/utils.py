def parse_balance(balances):
    return {
        b["currency"]: {"available": b["available"], "balance": b["balance"]}
        for b in balances
    }
