"""JSON por stdin a stdout. No acepta rutas, no lee datasets ni escribe archivos."""

import json
import sys

from . import VERSION, validate_label, validate_records, validate_week


def main():
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict) or set(data) - {"records", "weeks", "labels"}:
            raise ValueError("Formato de entrada desconocido")
        if not data or any(not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows)
                           for rows in data.values()):
            raise ValueError("Se requieren listas de objetos")
        groups = {"records": validate_records(data.get("records", [])),
                  "weeks": [validate_week(row) for row in data.get("weeks", [])],
                  "labels": [validate_label(row) for row in data.get("labels", [])]}
        output = {"version": VERSION, "training_authorized": False,
                  "results": {name: [[check.to_dict() for check in checks] for checks in rows]
                              for name, rows in groups.items()}}
        json.dump(output, sys.stdout, ensure_ascii=True, allow_nan=False)
        sys.stdout.write("\n")
        return int(any(check.status == "invalido" for rows in groups.values() for checks in rows for check in checks))
    except (ValueError, TypeError):
        # No repetir valores de entrada: pueden ser sensibles en una futura integración.
        sys.stderr.write("Entrada inválida; se requiere JSON conforme al contrato del validador.\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
