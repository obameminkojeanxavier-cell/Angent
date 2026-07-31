"""
Moteur d'exécution des skills.

Ce module implémente un système d'exécution sophistiqué pour les skills importés
via ZIP, permettant de distinguer entre les fichiers d'interface, les modèles,
les ressources et les générateurs, et de produire des livrables dans différents
formats (HTML, PDF, Markdown, JSON, etc.).
"""
import os
import re
import tempfile
import subprocess
import zipfile
from pathlib import Path


def detect_skill_root(extract_dir: Path) -> Path:
    """Détecte automatiquement la racine du skill en cherchant SKILL.md."""
    skill_files = list(extract_dir.rglob("SKILL.md"))
    
    if not skill_files:
        raise ValueError("Aucun fichier SKILL.md trouvé dans le package.")
    
    if len(skill_files) > 1:
        raise ValueError("Plusieurs racines de skill détectées dans le package.")
    
    return skill_files[0].parent


def validate_zip_structure(extract_dir: Path) -> None:
    """Valide la structure du ZIP extrait."""
    # Vérifier que SKILL.md existe
    skill_files = list(extract_dir.rglob("SKILL.md"))
    if not skill_files:
        raise ValueError("Aucun fichier SKILL.md trouvé dans le package.")
    
    if len(skill_files) > 1:
        raise ValueError("Plusieurs racines de skill détectées dans le package.")
    
    # Vérifier l'absence de chemins dangereux (.. dans les chemins relatifs)
    for file_path in extract_dir.rglob("*"):
        if file_path.is_file():
            try:
                relative = file_path.relative_to(extract_dir)
                # Vérifier que le chemin résolu reste dans extract_dir
                resolved = (extract_dir / relative).resolve()
                if not str(resolved).startswith(str(extract_dir.resolve())):
                    raise ValueError(f"Chemin dangereux détecté : {relative}")
            except ValueError:
                # Erreur lors du calcul du chemin relatif
                raise ValueError(f"Chemin invalide détecté : {file_path}")


class SkillExecutor:
    """Moteur d'exécution des skills."""
    
    def __init__(self, skill, params):
        self.skill = skill
        self.params = params
        self.files = {f.path: f for f in skill.files.all()}
    
    def execute(self):
        """Exécute le skill et retourne le résultat."""
        # Déterminer le type d'exécution selon le point d'entrée
        entry_point = self.skill.entry_point
        
        if not entry_point:
            # Auto-détection du point d'entrée
            entry_point = self._detect_entry_point()
        
        if not entry_point:
            raise ValueError("Aucun point d'entrée trouvé dans le skill")
        
        # Exécuter selon le type de fichier
        if entry_point.endswith('.py'):
            return self._execute_python(entry_point)
        elif entry_point.endswith('.html'):
            return self._execute_html_template(entry_point)
        elif entry_point.endswith('.md'):
            return self._execute_markdown(entry_point)
        else:
            # Fallback : traiter comme template
            return self._execute_template(entry_point)
    
    def _detect_entry_point(self):
        """Détecte automatiquement le point d'entrée du skill."""
        # Priorité : scripts/*.py > generator.py > main.py > template.html > index.html > SKILL.md
        candidates = [
            'scripts/bfev_pipeline.py',
            'scripts/pipeline.py',
            'scripts/generator.py',
            'scripts/main.py',
            'generator.py',
            'main.py',
            'run.py',
            'execute.py',
            'template.html',
            'index.html',
            'output.html',
            'SKILL.md',
        ]
        
        for candidate in candidates:
            if candidate in self.files:
                return candidate
        
        # Chercher n'importe quel script dans scripts/
        for path in sorted(self.files.keys()):
            if path.startswith('scripts/') and path.endswith('.py'):
                return path
        
        # Sinon, prendre le premier fichier non-MD
        for path in sorted(self.files.keys()):
            if not path.lower().endswith('.md'):
                return path
        
        return None
    
    def _execute_python(self, entry_point):
        """Exécute un script Python."""
        file_obj = self.files.get(entry_point)
        if not file_obj:
            raise FileNotFoundError(f"Fichier introuvable : {entry_point}")
        
        # Créer un environnement temporaire
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            
            # Écrire tous les fichiers du skill dans le répertoire temporaire
            for path, file_obj in self.files.items():
                file_path = tmpdir_path / path
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(file_obj.content)
            
            # Valider la structure et détecter la racine du skill
            validate_zip_structure(tmpdir_path)
            skill_root = detect_skill_root(tmpdir_path)
            
            # Mapping des paramètres vers les arguments CLI (selon bfev_pipeline.py)
            param_mapping = {
                'content': 'text',
                'document_type': 'document-type',
                'entity': 'entity',
                'title': 'title',
                'subtitle': 'subtitle',
                'date': 'date',
                'template': 'template',
                'logo': 'logo',
                'format': 'format',
                'catalog': 'catalog',
                'entity_catalog': 'entity-catalog',
            }
            
            # Paramètres booléens qui n'ont pas de valeur (selon bfev_pipeline.py)
            boolean_params = {'pdf', 'analyze_only', 'no_cache'}
            
            # Générer automatiquement un chemin de sortie si non fourni
            output_path = self.params.get('output')
            if not output_path:
                # Créer un dossier de sortie temporaire
                import uuid
                task_id = str(uuid.uuid4())[:8]
                output_dir = Path('/tmp/datahub-skills') / self.skill.name / task_id
                output_dir.mkdir(parents=True, exist_ok=True)
                
                # Générer un nom de fichier sécurisé
                document_type = self.params.get('document_type', 'document').replace('_', '-')
                output_filename = f"{document_type}.docx"
                output_path = str(output_dir / output_filename)
            
            # Construire le chemin du script relatif à la racine du skill
            script_path = skill_root / entry_point
            if not script_path.exists():
                raise FileNotFoundError(f"Script introuvable : {script_path}")
            
            # Construire les arguments de ligne de commande
            args = ['python', str(script_path)]
            
            # Ajouter le chemin de sortie (obligatoire selon bfev_pipeline.py)
            args.append('--output')
            args.append(output_path)
            
            # Ajouter les paramètres comme arguments
            for key, value in self.params.items():
                # Mapping des noms de paramètres
                cli_key = param_mapping.get(key, key)
                
                # Gestion des formats de sortie (convertir en flag --pdf)
                if key == 'output_format' and value == 'pdf':
                    args.append('--pdf')
                # Gestion des paramètres booléens
                elif key in boolean_params or (isinstance(value, bool) and value):
                    args.append(f'--{cli_key}')
                # Gestion des paramètres avec valeur (sauf output déjà ajouté)
                elif key != 'output' and value is not None and value != '':
                    args.append(f'--{cli_key}')
                    args.append(str(value))
            
            # Préparer les variables d'environnement
            env = os.environ.copy()
            for key, value in self.params.items():
                env[f'SKILL_{key.upper()}'] = str(value)
            
            # Afficher la commande pour débogage
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"Executing skill {self.skill.name} from root {skill_root} with command: {' '.join(args)}")
            
            # Exécuter le script depuis la racine du skill
            try:
                result = subprocess.run(
                    args,
                    cwd=skill_root,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                
                if result.returncode != 0:
                    raise RuntimeError(f"Erreur d'exécution : {result.stderr}")
                
                # Chercher les fichiers générés (PDF, DOCX, etc.)
                generated_files = []
                for root, dirs, files in os.walk(skill_root):
                    for file in files:
                        file_path = Path(root) / file
                        # Ignorer les fichiers originaux du skill
                        relative_path = file_path.relative_to(skill_root)
                        if str(relative_path) not in self.files:
                            generated_files.append(file_path)
                
                # Chercher aussi dans le dossier de sortie spécifié
                if Path(output_path).exists():
                    output_file = Path(output_path)
                    if output_file.suffix.lower() == '.pdf':
                        with open(output_file, 'rb') as f:
                            pdf_content = f.read()
                        return {
                            'content': pdf_content,
                            'content_type': 'application/pdf',
                            'output_type': 'pdf',
                        }
                    elif output_file.suffix.lower() == '.docx':
                        with open(output_file, 'rb') as f:
                            docx_content = f.read()
                        return {
                            'content': docx_content,
                            'content_type': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                            'output_type': 'docx',
                        }
                
                # Priorité aux fichiers PDF dans skill_root
                pdf_files = [f for f in generated_files if f.suffix.lower() == '.pdf']
                if pdf_files:
                    pdf_file = pdf_files[0]
                    with open(pdf_file, 'rb') as f:
                        pdf_content = f.read()
                    return {
                        'content': pdf_content,
                        'content_type': 'application/pdf',
                        'output_type': 'pdf',
                    }
                
                # Sinon, chercher DOCX
                docx_files = [f for f in generated_files if f.suffix.lower() == '.docx']
                if docx_files:
                    docx_file = docx_files[0]
                    with open(docx_file, 'rb') as f:
                        docx_content = f.read()
                    return {
                        'content': docx_content,
                        'content_type': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                        'output_type': 'docx',
                    }
                
                # Sinon, retourner stdout
                output = result.stdout
                output_type = self._detect_output_type(output)
                
                return {
                    'content': output,
                    'content_type': output_type,
                    'output_type': output_type,
                }
            except subprocess.TimeoutExpired:
                raise RuntimeError("Timeout lors de l'exécution du script")
    
    def _execute_html_template(self, entry_point):
        """Exécute un template HTML."""
        file_obj = self.files.get(entry_point)
        if not file_obj:
            raise FileNotFoundError(f"Fichier introuvable : {entry_point}")
        
        content = file_obj.content
        
        # Remplacer les paramètres dans le template
        for key, value in self.params.items():
            content = content.replace(f'{{{key}}}', str(value))
            content = content.replace(f'{{{{ {key} }}}}', str(value))
        
        # Si le skill demande du PDF, convertir
        if self.skill.output_type == 'pdf':
            return self._convert_to_pdf(content)
        
        return {
            'content': content,
            'content_type': 'text/html',
            'output_type': 'html',
        }
    
    def _execute_markdown(self, entry_point):
        """Exécute un template Markdown."""
        file_obj = self.files.get(entry_point)
        if not file_obj:
            raise FileNotFoundError(f"Fichier introuvable : {entry_point}")
        
        content = file_obj.content
        
        # Remplacer les paramètres
        for key, value in self.params.items():
            content = content.replace(f'{{{key}}}', str(value))
        
        return {
            'content': content,
            'content_type': 'text/markdown',
            'output_type': 'markdown',
        }
    
    def _execute_template(self, entry_point):
        """Exécute un template générique."""
        file_obj = self.files.get(entry_point)
        if not file_obj:
            raise FileNotFoundError(f"Fichier introuvable : {entry_point}")
        
        content = file_obj.content
        
        # Remplacer les paramètres
        for key, value in self.params.items():
            content = content.replace(f'{{{key}}}', str(value))
        
        return {
            'content': content,
            'content_type': file_obj.content_type,
            'output_type': self.skill.output_type,
        }
    
    def _detect_output_type(self, content):
        """Détecte le type de contenu."""
        content_lower = content.lower()
        
        if content_lower.startswith('<!doctype html') or content_lower.startswith('<html'):
            return 'text/html'
        elif content_lower.startswith('{') or content_lower.startswith('['):
            return 'application/json'
        elif content_lower.startswith('#') or content_lower.startswith('##'):
            return 'text/markdown'
        else:
            return 'text/plain'
    
    def _convert_to_pdf(self, html_content):
        """Convertit le contenu HTML en PDF."""
        try:
            # Essayer avec weasyprint
            import weasyprint
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
                pdf_path = tmp.name
            
            weasyprint.HTML(string=html_content).write_pdf(pdf_path)
            
            with open(pdf_path, 'rb') as f:
                pdf_content = f.read()
            
            os.unlink(pdf_path)
            
            return {
                'content': pdf_content,
                'content_type': 'application/pdf',
                'output_type': 'pdf',
            }
        except ImportError:
            # Fallback : essayer avec wkhtmltopdf
            try:
                with tempfile.NamedTemporaryFile(suffix='.html', delete=False) as html_tmp:
                    html_tmp.write(html_content.encode('utf-8'))
                    html_path = html_tmp.name
                
                with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as pdf_tmp:
                    pdf_path = pdf_tmp.name
                
                subprocess.run(
                    ['wkhtmltopdf', html_path, pdf_path],
                    capture_output=True,
                    timeout=30
                )
                
                with open(pdf_path, 'rb') as f:
                    pdf_content = f.read()
                
                os.unlink(html_path)
                os.unlink(pdf_path)
                
                return {
                    'content': pdf_content,
                    'content_type': 'application/pdf',
                    'output_type': 'pdf',
                }
            except (FileNotFoundError, subprocess.SubprocessError):
                # Si PDF non disponible, retourner HTML avec avertissement
                return {
                    'content': html_content,
                    'content_type': 'text/html',
                    'output_type': 'html',
                    'warning': 'Conversion PDF non disponible, HTML retourné à la place',
                }
