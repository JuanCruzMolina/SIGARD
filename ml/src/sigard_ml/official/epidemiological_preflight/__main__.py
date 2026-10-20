"""Preflight por stdin/stdout, sin aceptar rutas ni invocar un entrenamiento."""

import json
import sys

from . import SimulatedArtifact, run_preflight


def main():
    try:
        if len(sys.argv) > 1:
            raise ValueError("No se admiten argumentos ni rutas")
        payload = json.load(sys.stdin)
        allowed = {"bundle", "artifacts", "decision_refs", "requested_action"}
        if not isinstance(payload, dict) or "bundle" not in payload or set(payload) - allowed:
            raise ValueError("Contrato de entrada desconocido")
        artifacts = payload.get("artifacts", {})
        if not isinstance(artifacts, dict):
            raise ValueError("Registro inválido")
        registry = {}
        for reference, value in artifacts.items():
            if (not isinstance(value, dict) or set(value) != {"content", "sha256"}
                    or not isinstance(value["content"], str) or not isinstance(value["sha256"], str)):
                raise ValueError("Respaldo inválido")
            registry[reference] = SimulatedArtifact(value["content"].encode("utf-8"), value["sha256"])
        report = run_preflight(payload["bundle"], artifacts=registry,
                               decision_refs=payload.get("decision_refs"),
                               requested_action=payload.get("requested_action", "inspect"))
        json.dump(report.to_dict(), sys.stdout, ensure_ascii=True, allow_nan=False)
        sys.stdout.write("\n")
        return 0 if report.permitted_uses else 1
    except (ValueError, TypeError, UnicodeError, OverflowError):
        sys.stderr.write("Entrada inválida: se requiere JSON conforme al contrato del preflight ficticio.\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
