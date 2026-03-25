import os
import logging
import pypandoc

logger = logging.getLogger(__name__)


class ExportService:
    def __init__(self, template_path="resources/templates/default.docx"):
        # Resolve the template path relative to the application root
        app_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

        # Determine if it's an absolute path or relative to root
        if template_path:
            if not os.path.isabs(template_path):
                self.template_path = os.path.abspath(
                    os.path.join(app_root, template_path)
                )
            else:
                self.template_path = template_path
        else:
            self.template_path = None

        # Download pandoc on startup if not present (Option A)
        try:
            pypandoc.get_pandoc_version()
        except OSError:
            logger.info(
                "Pandoc not found. Attempting to download pandoc to assets/tools..."
            )
            tools_dir = os.path.join(app_root, "assets", "tools")
            os.makedirs(tools_dir, exist_ok=True)
            pypandoc.download_pandoc(targetfolder=tools_dir)
            # Add to PATH so pypandoc finds it in subsequent calls
            os.environ["PATH"] += os.pathsep + tools_dir

    def render_markdown_to_docx(self, md_content: str, output_path: str):
        """
        Takes raw markdown, converts it via pypandoc, and injects it into a
        Word template.
        """
        extra_args = []
        if self.template_path:
            if os.path.isfile(self.template_path):
                extra_args.append(f"--reference-doc={self.template_path}")
            else:
                # If explicit template was passed but doesn't exist, raise clear error
                raise ValueError(
                    f"Specified template file does not exist: {self.template_path}"
                )

        # Convert using pypandoc
        try:
            pypandoc.convert_text(
                source=md_content,
                to="docx",
                format="md",
                outputfile=output_path,
                extra_args=extra_args,
            )
        except Exception as e:
            raise ValueError(f"Pandoc conversion failed: {e}") from e

        return output_path
