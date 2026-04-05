with open('gui/components/question_block.py', 'r') as f:
    content = f.read()

# Fix the event filter issue
old_event_filter = """    def eventFilter(self, obj, event):
        if obj == self.text_edit and event.type() == QFocusEvent.FocusOut:
            # We want to delay the exit slightly in case focus shifts within the widget
            QTimer.singleShot(100, self._check_focus_and_exit)
        return super().eventFilter(obj, event)"""

new_event_filter = """    def eventFilter(self, obj, event):
        if hasattr(self, 'text_edit') and obj == self.text_edit and event.type() == QFocusEvent.FocusOut:
            # We want to delay the exit slightly in case focus shifts within the widget
            QTimer.singleShot(100, self._check_focus_and_exit)
        return super().eventFilter(obj, event)"""

content = content.replace(old_event_filter, new_event_filter)

with open('gui/components/question_block.py', 'w') as f:
    f.write(content)
