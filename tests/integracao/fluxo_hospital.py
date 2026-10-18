"""Testes integrados do fluxo do perfil Hospital do MedSinc em ambiente local (18/10/2026).

Complementa o api_medico.py (fluxo do médico): cadastro do hospital, publicação de vaga, candidatura do médico, aprovação,
lotação da vaga, conflito de horário e o plantão gerado na agenda do médico. Usuários e dados de teste são criados
pelo próprio script. Grava resultado_fluxo_hospital.json.

Uso: python3 tests/integracao/fluxo_hospital.py [--base http://127.0.0.1:5055]
Só biblioteca padrão. Nada roda no import.
"""
import argparse
import importlib.util
import json
from datetime import date, datetime, timedelta
from pathlib import Path

PASTA = Path(__file__).parent
SAIDA = PASTA / "resultado_fluxo_hospital.json"


def _chamar():
    """Reaproveita a função chamar() do script api_medico.py (mesmo cliente HTTP e mesma medição de tempo)."""
    spec = importlib.util.spec_from_file_location("testes09", PASTA / "api_medico.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.chamar


def _medico(chamar, base, sufixo):
    """Cadastra e autentica um médico de teste; devolve o token."""
    email = f"medico.hosp{sufixo}@exemplo.com"
    chamar(base, "POST", "/api/doctors/", {"name": f"Médico {sufixo}", "email": email, "password": "Senha#Teste123",
                                           "main_specialty": "Clínica Médica", "graduation_university": "Universidade Exemplo",
                                           "phone": "(00) 00000-0000", "accepted_terms": True,
                                           "crm": sufixo, "crm_state": "PR", "council_number": sufixo, "council_state": "PR"})
    _, c, _ = chamar(base, "POST", "/api/login", {"email": email, "password": "Senha#Teste123"})
    return (c or {}).get("access_token") or (c or {}).get("token") if isinstance(c, dict) else None


def executar(base: str) -> list:
    """Executa os casos H01–H12 e devolve a lista de resultados."""
    chamar = _chamar()
    res = []
    sufixo = datetime.now().strftime("%H%M%S")

    def caso(cid, desc, st, corpo, ms, ok):
        res.append({"caso": cid, "descricao": desc, "status_http": st, "tempo_ms": round(ms, 1), "passou": bool(ok),
                    "detalhe": (corpo if isinstance(corpo, str) else json.dumps(corpo, ensure_ascii=False))[:200]})

    st, c, ms = chamar(base, "POST", "/api/auth/hospital/register", {
        "hospital": {"name": f"Hospital Teste {sufixo}", "address": "Rua Exemplo, 200", "latitude": -24.95,
                     "longitude": -53.45, "city": "Cascavel", "state": "PR"},
        "admin": {"name": "Gestora Teste", "email": f"gestor{sufixo}@exemplo.com", "password": "Senha#Teste123"},
        "accepted_terms": True})
    tok_h = (c or {}).get("token") or (c or {}).get("access_token") if isinstance(c, dict) else None
    caso("H01", "Cadastro de hospital com administrador", st, c, ms, st in (200, 201) and tok_h)
    st, c, ms = chamar(base, "GET", "/api/hospital/me", None, tok_h)
    caso("H02", "Hospital autenticado consulta o próprio perfil", st, c, ms, st == 200)

    tok_m1 = _medico(chamar, base, sufixo + "1")
    tok_m2 = _medico(chamar, base, sufixo + "2")
    dia = date.today() + timedelta(days=10)
    vaga = {"date": str(dia), "start_time": "07:00", "end_time": "19:00", "specialty": "Clínica Médica",
            "value": 1400.0, "payment_date": str(dia + timedelta(days=30)), "slots_total": 1, "notes": "Vaga de teste"}
    st, c, ms = chamar(base, "POST", "/api/marketplace/opportunities", vaga, tok_m1)
    caso("H03", "Médico não pode publicar vaga (perfil errado)", st, c, ms, st in (401, 403))
    st, c, ms = chamar(base, "POST", "/api/marketplace/opportunities", vaga, tok_h)
    opp = ((c or {}).get("opportunity") or {}).get("id") if isinstance(c, dict) else None
    caso("H04", "Hospital publica vaga de plantão", st, c, ms, st == 201 and opp)

    st, c, ms = chamar(base, "GET", "/api/marketplace/opportunities", None, tok_m1)
    lista = c if isinstance(c, list) else (c or {}).get("opportunities", []) if isinstance(c, dict) else []
    caso("H05", "Médico encontra a vaga publicada", st, f"{len(lista)} vagas", ms,
         st == 200 and any(isinstance(o, dict) and o.get("id") == opp for o in lista))
    st, c, ms = chamar(base, "POST", f"/api/marketplace/opportunities/{opp}/apply", {}, tok_m1)
    app_id = None
    if isinstance(c, dict):
        app_id = c.get("id") or (c.get("application") or {}).get("id")
    caso("H06", "Médico se candidata à vaga", st, c, ms, st in (200, 201))
    st, c, ms = chamar(base, "POST", f"/api/marketplace/opportunities/{opp}/apply", {}, tok_m1)
    caso("H07", "Candidatura repetida é recusada", st, c, ms, st in (400, 409))
    st, c, ms = chamar(base, "GET", f"/api/marketplace/opportunities/{opp}/applications", None, tok_h)
    cands = c if isinstance(c, list) else (c or {}).get("applications", []) if isinstance(c, dict) else []
    if not app_id and cands:
        app_id = cands[0].get("id")
    caso("H08", "Hospital vê a candidatura recebida", st, f"{len(cands)} candidaturas", ms, st == 200 and len(cands) >= 1)
    st, c, ms = chamar(base, "POST", f"/api/marketplace/applications/{app_id}/approve", {}, tok_h)
    caso("H09", "Hospital aprova a candidatura", st, c, ms, st == 200)

    st, c, ms = chamar(base, "GET", "/api/shifts/", None, tok_m1)
    turnos = c if isinstance(c, list) else (c or {}).get("shifts", []) if isinstance(c, dict) else []
    caso("H10", "Plantão aprovado aparece na agenda do médico", st, f"{len(turnos)} plantões", ms,
         st == 200 and any(isinstance(t, dict) and str(t.get("date", ""))[:10] == str(dia) for t in turnos))
    st, c, ms = chamar(base, "POST", f"/api/marketplace/opportunities/{opp}/apply", {}, tok_m2)
    caso("H11", "Vaga lotada (1 de 1) não aceita nova candidatura", st, c, ms, st in (400, 409))

    vaga2 = dict(vaga, start_time="12:00", end_time="18:00", notes="Vaga sobreposta")
    st2, c2, _ = chamar(base, "POST", "/api/marketplace/opportunities", vaga2, tok_h)
    opp2 = ((c2 or {}).get("opportunity") or {}).get("id") if isinstance(c2, dict) else None
    st, c, ms = chamar(base, "POST", f"/api/marketplace/opportunities/{opp2}/apply", {}, tok_m1)
    caso("H12", "Candidatura em horário que conflita com plantão já assumido é recusada", st, c, ms, st in (400, 409))
    return res


def main() -> None:
    """Executa os testes do fluxo do hospital e grava o JSON de resultados."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:5055")
    a = ap.parse_args()
    res = executar(a.base)
    SAIDA.write_text(json.dumps({"executado_em": datetime.now().isoformat(timespec="seconds"),
                                 "ambiente": "local: gunicorn 2 workers + MySQL 8.0 (Docker) no MacBook M1",
                                 "aprovados": sum(r["passou"] for r in res), "total": len(res), "casos": res},
                                ensure_ascii=False, indent=1))
    for r in res:
        print(("OK " if r["passou"] else "FALHOU ") + r["caso"], r["descricao"], r["status_http"], f'{r["tempo_ms"]} ms',
              "" if r["passou"] else r["detalhe"])


if __name__ == "__main__":
    main()
