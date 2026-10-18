"""Testes funcionais e de carga da API do MedSinc em ambiente local (18/10/2026).

Roda contra o backend Flask local (gunicorn em 127.0.0.1:5055, MySQL 8 em Docker), com dados e usuário de teste
criados pelo próprio script. Gera resultado_api_medico.json com cada caso funcional (passou/falhou, status HTTP,
tempo) e as estatísticas de carga (média, p50, p95, máximo, vazão e taxa de erro).

Uso: python3 tests/integracao/api_medico.py [--base http://127.0.0.1:5055] [--usuarios 10] [--segundos 60]
Só biblioteca padrão. Nada roda no import.
"""
import argparse
import json
import statistics
import threading
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

SAIDA = Path(__file__).with_name("resultado_api_medico.json")


def chamar(base: str, metodo: str, rota: str, corpo: dict | None = None, token: str | None = None):
    """Faz uma requisição JSON e devolve (status, json ou texto, tempo em ms)."""
    dados = json.dumps(corpo).encode() if corpo is not None else None
    req = urllib.request.Request(base + rota, data=dados, method=metodo)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            st, txt = r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        st, txt = e.code, e.read().decode()
    except Exception as e:  # rede, timeout
        st, txt = 0, str(e)
    ms = (time.perf_counter() - t0) * 1000
    try:
        return st, json.loads(txt), ms
    except Exception:
        return st, txt, ms


def funcionais(base: str) -> tuple[list, str]:
    """Executa os casos funcionais do fluxo do médico e devolve (resultados, token)."""
    res = []
    sufixo = datetime.now().strftime("%H%M%S")
    email = f"medico.teste{sufixo}@exemplo.com"

    def caso(cid, desc, st, corpo, ms, ok):
        res.append({"caso": cid, "descricao": desc, "status_http": st, "tempo_ms": round(ms, 1),
                    "passou": bool(ok), "detalhe": (corpo if isinstance(corpo, str) else json.dumps(corpo, ensure_ascii=False))[:200]})

    st, c, ms = chamar(base, "POST", "/api/doctors/", {"name": "Médico Teste", "email": email, "password": "Senha#Teste123",
                                                     "main_specialty": "Clínica Médica", "graduation_university": "Universidade Exemplo",
                                                     "phone": "(00) 00000-0000", "accepted_terms": True,
                                                     "crm": sufixo, "crm_state": "PR", "council_number": sufixo, "council_state": "PR"})
    caso("F01", "Cadastro de médico com universidade de formação", st, c, ms, st in (200, 201))
    st, c, ms = chamar(base, "POST", "/api/login", {"email": email, "password": "Senha#Teste123"})
    token = (c or {}).get("access_token") or (c or {}).get("token") if isinstance(c, dict) else None
    caso("F02", "Login do médico (JWT)", st, c, ms, st == 200 and token)
    st, c, ms = chamar(base, "POST", "/api/login", {"email": email, "password": "errada"})
    caso("F03", "Login com senha errada é recusado", st, c, ms, st in (400, 401, 403))
    st, c, ms = chamar(base, "GET", "/api/shifts/")
    caso("F04", "Rota protegida sem token é recusada", st, c, ms, st in (401, 403))

    st, c, ms = chamar(base, "POST", "/api/hospitals/", {"name": "Hospital Exemplo", "address": "Rua Exemplo, 100",
                                                         "latitude": -24.95, "longitude": -53.45}, token)
    hid = None
    if isinstance(c, dict):
        hid = c.get("id") or (c.get("hospital") or {}).get("id")
    if not hid:
        st2, lista, _ = chamar(base, "GET", "/api/hospitals/", None, token)
        if isinstance(lista, list) and lista:
            hid = lista[-1].get("id")
    caso("F05", "Cadastro de hospital", st, c, ms, st in (200, 201) and hid)
    # 18/10: GET /api/payments/ responde 500 (PaymentRepository sem get_all) — registrado como defeito encontrado.

    hoje = date.today()
    st, c, ms = chamar(base, "POST", "/api/shifts/", {"hospital_id": hid, "date": str(hoje + timedelta(days=2)),
                                                      "start_time": "07:00", "end_time": "19:00", "value": 1200.0,
                                                      "specialty": "Clínica Médica", "payment_date": str(hoje + timedelta(days=30))}, token)
    caso("F06", "Cadastro de plantão avulso (gera pagamento)", st, c, ms, st in (200, 201))
    st, c, ms = chamar(base, "POST", "/api/shifts/", {"hospital_id": hid, "date": str(hoje + timedelta(days=1)),
                                                      "week_days": [str(hoje + timedelta(days=(5 - hoje.weekday()) % 7 + 7 * k)) for k in range(4)],
                                                      "start_time": "07:00", "end_time": "19:00", "value": 1500.0,
                                                      "specialty": "Clínica Médica", "payment_date": str(hoje + timedelta(days=30))}, token)
    caso("F07", "Plantões recorrentes (4 sábados) criados de uma vez", st, c, ms,
         st in (200, 201) and isinstance(c, dict) and str(c.get("message", "")).startswith("4 "))
    st, c, ms = chamar(base, "GET", "/api/shifts/", None, token)
    n = len(c) if isinstance(c, list) else len((c or {}).get("shifts", [])) if isinstance(c, dict) else 0
    caso("F08", "Listagem de plantões traz o avulso + os 4 recorrentes", st, f"{n} plantões", ms, st == 200 and n >= 5)
    st, c, ms = chamar(base, "GET", "/api/payments/", None, token)
    caso("F09", "Pagamentos gerados para os plantões (inclusive recorrentes)", st, c if not isinstance(c, list) else f"{len(c)} pagamentos", ms, st == 200)

    st, cats, _ = chamar(base, "GET", "/api/expenses/categories", None, token)
    cat = None
    if isinstance(cats, list) and cats:
        cat = cats[0].get("value") if isinstance(cats[0], dict) else cats[0]
    elif isinstance(cats, dict):
        lst = cats.get("categories") or []
        cat = (lst[0].get("value") if lst and isinstance(lst[0], dict) else (lst[0] if lst else None))
    st, c, ms = chamar(base, "POST", "/api/expenses/", {"category": cat, "amount": 600.0, "expense_date": str(hoje),
                                                        "installments": 3, "description": "Gasto teste parcelado"}, token)
    caso("F10", "Gasto com parcelas definidas (3x)", st, c, ms, st in (200, 201))
    st, c, ms = chamar(base, "POST", "/api/expenses/", {"category": cat, "amount": 10.0, "expense_date": str(hoje),
                                                        "installments": 99}, token)
    caso("F11", "Parcelas fora do limite (99) são recusadas", st, c, ms, st == 400)
    st, c, ms = chamar(base, "POST", "/api/patients/", {"name": "Paciente Exemplo", "phone": "(00) 00000-0000",
                                                        "cpf": "529.982.247-25"}, token)
    caso("F12", "Cadastro de paciente com telefone e CPF", st, c, ms, st in (200, 201))
    st, c, ms = chamar(base, "POST", "/api/patients/", {"name": "Paciente Duplicado", "phone": "(00) 00000-0000",
                                                        "cpf": "529.982.247-25"}, token)
    caso("F13", "CPF duplicado é recusado", st, c, ms, st in (400, 409, 422))
    st, c, ms = chamar(base, "GET", "/api/patients/attendances/summary", None, token)
    caso("F14", "Resumo de atendimentos (base do gráfico de pacientes/mês)", st, c, ms, st == 200)
    st, c, ms = chamar(base, "GET", "/api/expenses/summary", None, token)
    caso("F15", "Resumo financeiro de gastos", st, c, ms, st == 200)
    return res, token


def carga(base: str, token: str, usuarios: int, segundos: int) -> dict:
    """Usuários simultâneos repetindo as leituras mais comuns do médico durante N segundos."""
    rotas = ["/api/shifts/", "/api/patients/", "/api/expenses/summary", "/api/patients/attendances/summary"]
    tempos, erros, lock = [], [0], threading.Lock()
    fim = time.time() + segundos

    def trabalhador(i):
        k = i
        while time.time() < fim:
            st, _, ms = chamar(base, "GET", rotas[k % len(rotas)], None, token)
            k += 1
            with lock:
                tempos.append(ms)
                if st != 200:
                    erros[0] += 1

    th = [threading.Thread(target=trabalhador, args=(i,)) for i in range(usuarios)]
    t0 = time.time()
    for t in th:
        t.start()
    for t in th:
        t.join()
    dur = time.time() - t0
    ts = sorted(tempos)
    p = lambda q: round(ts[min(len(ts) - 1, int(q * len(ts)))], 1) if ts else None
    return {"usuarios_simultaneos": usuarios, "duracao_s": round(dur, 1), "requisicoes": len(ts),
            "vazao_req_s": round(len(ts) / dur, 1) if dur else None, "media_ms": round(statistics.mean(ts), 1) if ts else None,
            "p50_ms": p(0.5), "p95_ms": p(0.95), "max_ms": round(ts[-1], 1) if ts else None,
            "erros": erros[0], "taxa_erro_pct": round(100 * erros[0] / len(ts), 2) if ts else None, "rotas": rotas}


def main() -> None:
    """Executa os testes e grava o JSON de resultados."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:5055")
    ap.add_argument("--usuarios", type=int, nargs="+", default=[1, 10, 25])
    ap.add_argument("--segundos", type=int, default=30)
    a = ap.parse_args()
    res, token = funcionais(a.base)
    cargas = [carga(a.base, token, u, a.segundos) for u in a.usuarios] if token else []
    saida = {"executado_em": datetime.now().isoformat(timespec="seconds"),
             "ambiente": "local: gunicorn 2 workers + MySQL 8.0 (Docker) no MacBook M1; cliente urllib na mesma máquina",
             "funcionais": res, "aprovados": sum(r["passou"] for r in res), "total": len(res), "carga": cargas}
    SAIDA.write_text(json.dumps(saida, ensure_ascii=False, indent=1))
    print(json.dumps({k: v for k, v in saida.items() if k != "funcionais"}, ensure_ascii=False, indent=1))
    for r in res:
        print(("OK " if r["passou"] else "FALHOU ") + r["caso"], r["descricao"], r["status_http"], f'{r["tempo_ms"]} ms')


if __name__ == "__main__":
    main()
