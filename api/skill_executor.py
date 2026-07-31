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
from pathlib import Path


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
        # Priorité : generator.py > main.py > template.html > index.html > SKILL.md
        candidates = [
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
            # Écrire tous les fichiers du skill dans le répertoire temporaire
            for path, file_obj in self.files.items():
                file_path = Path(tmpdir) / path
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(file_obj.content)
            
            # Préparer les paramètres comme variables d'environnement
            env = os.environ.copy()
            for key, value in self.params.items():
                env[f'SKILL_{key.upper()}'] = str(value)
            
            # Exécuter le script
            script_path = Path(tmpdir) / entry_point
            try:
                result = subprocess.run(
                    ['python', str(script_path)],
                    cwd=tmpdir,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if result.returncode != 0:
                    raise RuntimeError(f"Erreur d'exécution : {result.stderr}")
                
                output = result.stdout
                
                # Déterminer le type de sortie
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
