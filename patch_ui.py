with open('ui_calibration.py', 'r') as f:
    content = f.read()


# We want to replace mid_placeholder with some QuestionBlockWidget
# We will import the new widget
import_statement = "from gui.components.question_block import QuestionBlockWidget"
if import_statement not in content:
    content = import_statement + "\n" + content

# Replace placeholder logic with adding actual block widgets
old_logic = """        # Placeholder for the dual-state ElevatedCardWidget
        self.mid_placeholder = QLabel("流式双态编辑器 (Markdown / MathJax)")
        self.mid_placeholder.setAlignment(Qt.AlignCenter)
        self.mid_layout.addWidget(self.mid_placeholder)
        self.mid_layout.addStretch(1)"""

new_logic = """        # Instantiate dual-state ElevatedCardWidgets (QuestionBlockWidget)
        self.question_blocks = []
        for i in range(3):
            block = QuestionBlockWidget(self.mid_panel_content)
            block.set_question_number(i + 1)
            # Add some sample math markdown
            block.set_markdown(f"**Question {i+1}**\\n\\nSolve the equation: $$ x^2 - {i+4}x + 4 = 0 $$")
            self.mid_layout.addWidget(block)
            self.question_blocks.append(block)

        self.mid_layout.addStretch(1)"""

content = content.replace(old_logic, new_logic)

with open('ui_calibration.py', 'w') as f:
    f.write(content)
