"""
Tests pour le moteur d'exécution des skills.
"""
import os
import sys
import tempfile
import zipfile
from pathlib import Path

# Ajouter le répertoire parent au path pour importer les modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.skill_executor import detect_skill_root, validate_zip_structure


def test_detect_skill_root():
    """Teste la détection de la racine du skill."""
    # Cas 1: SKILL.md à la racine
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        skill_dir = tmpdir_path / "test-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Test Skill")
        
        root = detect_skill_root(tmpdir_path)
        assert root == skill_dir, f"Attendu {skill_dir}, obtenu {root}"
    
    # Cas 2: SKILL.md dans un sous-dossier
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        skill_dir = tmpdir_path / "nested" / "skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# Nested Skill")
        
        root = detect_skill_root(tmpdir_path)
        assert root == skill_dir, f"Attendu {skill_dir}, obtenu {root}"
    
    # Cas 3: Pas de SKILL.md
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        try:
            detect_skill_root(tmpdir_path)
            assert False, "Devrait lever ValueError"
        except ValueError as e:
            assert "Aucun fichier SKILL.md" in str(e)
    
    # Cas 4: Plusieurs SKILL.md
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        skill_dir1 = tmpdir_path / "multi1"
        skill_dir1.mkdir()
        (skill_dir1 / "SKILL.md").write_text("# Skill 1")
        
        skill_dir2 = tmpdir_path / "multi2"
        skill_dir2.mkdir()
        (skill_dir2 / "SKILL.md").write_text("# Skill 2")
        
        try:
            detect_skill_root(tmpdir_path)
            assert False, "Devrait lever ValueError"
        except ValueError as e:
            assert "Plusieurs racines" in str(e)
    
    print("✓ test_detect_skill_root passé")


def test_validate_zip_structure():
    """Teste la validation de la structure ZIP."""
    # Cas 1: Structure valide
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        skill_dir = tmpdir_path / "valid-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Valid Skill")
        (skill_dir / "script.py").write_text("print('hello')")
        
        validate_zip_structure(tmpdir_path)  # Ne doit pas lever d'exception
    
    # Cas 2: Pas de SKILL.md
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        skill_dir = tmpdir_path / "no-skill"
        skill_dir.mkdir()
        (skill_dir / "script.py").write_text("print('hello')")
        
        try:
            validate_zip_structure(tmpdir_path)
            assert False, "Devrait lever ValueError"
        except ValueError as e:
            assert "Aucun fichier SKILL.md" in str(e)
    
    print("✓ test_validate_zip_structure passé")


def test_skill_with_nested_structure():
    """Teste l'exécution d'un skill avec une structure imbriquée."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        
        # Créer une structure similaire à nedco-format
        skill_dir = tmpdir_path / "nedco-format"
        skill_dir.mkdir()
        
        (skill_dir / "SKILL.md").write_text("# NED&CO Format Skill")
        
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir()
        
        # Créer un script simple qui écrit un fichier de sortie
        script_content = """
import sys
import argparse
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--output', required=True)
parser.add_argument('--text')
args = parser.parse_args()

output = Path(args.output)
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(f"Generated: {args.text or 'default'}")
print(f"Created {output}")
"""
        (scripts_dir / "test_script.py").write_text(script_content)
        
        # Tester la détection de la racine
        root = detect_skill_root(tmpdir_path)
        assert root == skill_dir, f"Attendu {skill_dir}, obtenu {root}"
        
        # Tester que le script est accessible depuis la racine
        script_path = root / "scripts" / "test_script.py"
        assert script_path.exists(), f"Script introuvable: {script_path}"
    
    print("✓ test_skill_with_nested_structure passé")


if __name__ == "__main__":
    test_detect_skill_root()
    test_validate_zip_structure()
    test_skill_with_nested_structure()
    print("\n✓ Tous les tests passés")
