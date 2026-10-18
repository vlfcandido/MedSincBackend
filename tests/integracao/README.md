# Testes integrados da API

Scripts em Python puro (só biblioteca padrão) que exercitam a API de ponta a ponta contra um backend rodando.
Criam os próprios usuários e dados fictícios; **não rodar contra produção**.

| script | o que cobre |
|---|---|
| `api_medico.py` | 15 casos do fluxo do médico (cadastro, login, plantões avulso e recorrente, pagamentos, gastos parcelados, pacientes, resumos) e teste de carga com 1, 10 e 25 usuários simultâneos |
| `fluxo_hospital.py` | 12 casos do perfil Hospital (cadastro, publicação de vaga, candidatura, aprovação, lotação, conflito de horário e plantão na agenda do médico) |

## Como rodar
```bash
# backend local (ex.: gunicorn com 2 workers) apontando para um MySQL de teste
gunicorn -w 2 -b 127.0.0.1:5055 run:app
python3 tests/integracao/api_medico.py --base http://127.0.0.1:5055 --usuarios 1 10 25 --segundos 30
python3 tests/integracao/fluxo_hospital.py --base http://127.0.0.1:5055
```
Cada script imprime OK/FALHOU por caso e grava um JSON com status HTTP e tempo de cada caso (ignorado pelo git).

## Resultado em 18/10/2026 (ambiente local, MySQL 8 em Docker)
- Médico: 14/15 na 1ª rodada (F09, `GET /api/payments/` respondia 500), 15/15 após a correção deste PR.
- Hospital: 12/12. Candidatura e aprovação levaram 2,3–2,9 s porque o e-mail de notificação é enviado por SMTP dentro
  da requisição (sem servidor de e-mail local, o tempo inclui a tentativa de conexão).
- Carga: 0% de erro com até 25 usuários simultâneos; p95 entre 16 e 146 ms.
