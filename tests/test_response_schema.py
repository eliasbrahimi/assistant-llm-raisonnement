from __future__ import annotations

import unittest

from app.assistant_core import validate_four_block_response


# Vérifie qu'une réponse texte avec les 4 sections numérotées, dans l'ordre
# et non vides, est acceptée par le validateur.
class ResponseSchemaTest(unittest.TestCase):
    def test_four_block_validation(self) -> None:
        text = """
        1. Reformulation
        Reformulation courte.
        2. Raisonnement structuré
        Raisonnement court.
        3. Exemple
        Exemple court.
        4. Limites et vérification
        Vérification courte.
        """
        self.assertTrue(validate_four_block_response(text).valid)


if __name__ == "__main__":
    unittest.main()
