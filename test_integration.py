import asyncio
import os
import json
import uuid
from pathlib import Path
from fastapi.testclient import TestClient

# We will test the FastAPI app using TestClient to avoid needing to start the server in a separate process.
# This makes testing robust and independent of port bindings.

from src.screening.api.server import app
from src.screening.api.routes.screening import jobs
from unittest.mock import patch

class DummyGraph:
    async def ainvoke(self, *args, **kwargs):
        return {"decision": "ACCEPTED", "rejection_reasons": [], "justification": "Test mock output"}

client = TestClient(app)

@patch('src.screening.api.routes.screening.build_graph', return_value=DummyGraph())
def run_tests(mock_build_graph):
    print("--- INICIANDO BATERIA DE TESTES ---")
    
    # T1: UI e Health Check
    print("\n[T1] Testando Rota da UI (GET /)")
    resp_ui = client.get("/")
    if resp_ui.status_code == 200 and b"Start a" in resp_ui.content:
        print("SUCCESS: T1 Passou: UI renderizada com sucesso.")
    else:
        print(f"❌ T1 Falhou: status={resp_ui.status_code}, content={resp_ui.content[:100]}")
    
    # T2: Upload e Criação do Job
    print("\n[T2] Testando Upload e Criação de Job (POST /api/screen)")
    # Create a dummy CSV file
    dummy_csv = b"Title,Abstract\nTest Paper,This is a test abstract for screening.\n"
    
    files = {'file': ('dummy.csv', dummy_csv, 'text/csv')}
    data = {
        'inclusion': json.dumps(["Machine learning"]),
        'exclusion': json.dumps(["Review"]),
        'provider': 'gemini'
    }
    
    resp_upload = client.post("/api/screen", data=data, files=files)
    if resp_upload.status_code == 200:
        job_id = resp_upload.json().get("job_id")
        print(f"✅ T2 Passou: Job criado com ID {job_id}")
    else:
        print(f"❌ T2 Falhou: status={resp_upload.status_code}, detail={resp_upload.json()}")
        return

    # T3: Processamento do Job (Background Tasks)
    print("\n[T3] Testando Status do Job (GET /api/jobs/{job_id})")
    # No TestClient, background tasks are executed sequentially IN THE SAME THREAD right after the response is returned!
    # Because of this, by the time we check the status, the job should already be completed (or failed).
    resp_status = client.get(f"/api/jobs/{job_id}")
    if resp_status.status_code == 200:
        job_data = resp_status.json()
        print(f"✅ T3 Passou: Endpoint de status funcionou. Status atual: {job_data['status']}")
        print(f"   Detalhes: progress={job_data['progress']}/{job_data['total']}, error={job_data['error']}")
    else:
        print(f"❌ T3 Falhou: status={resp_status.status_code}, detail={resp_status.json()}")
    
    # T4: Download de Arquivos
    print("\n[T4] Testando Download de Resultados (GET /api/jobs/{job_id}/download)")
    resp_download = client.get(f"/api/jobs/{job_id}/download")
    if resp_download.status_code == 200:
        print("SUCCESS: T4 Passou: Arquivo baixado com sucesso.")
    else:
        print(f"❌ T4 Falhou: status={resp_download.status_code}, detail={resp_download.json() if resp_download.headers.get('content-type') == 'application/json' else resp_download.content[:100]}")

    print("\n--- FIM DOS TESTES ---")

if __name__ == "__main__":
    # We set a dummy API key so the LLM initialization doesn't throw immediate validation errors
    os.environ["GEMINI_API_KEY"] = "dummy_key_for_testing"
    run_tests()
