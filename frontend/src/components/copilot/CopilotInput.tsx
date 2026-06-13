import React, { useState, useRef, useEffect } from 'react';
import { ArrowUp } from 'lucide-react';

interface CopilotInputProps {
  onSend: (message: string) => void;
  disabled?: boolean;
}

export const CopilotInput: React.FC<CopilotInputProps> = ({ onSend, disabled = false }) => {
  const [text, setText] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleSubmit = () => {
    if (!text.trim() || disabled) return;
    onSend(text.trim());
    setText('');
  };

  // Auto-resize textarea heights
  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = 'auto';
    textarea.style.height = `${Math.min(textarea.scrollHeight, 120)}px`;
  }, [text]);

  return (
    <div className="p-3 bg-surface border-t border-border shrink-0 font-sans flex items-end gap-2 relative z-10">
      <div className="flex-1 relative flex bg-surface-2 border border-border focus-within:border-accent/40 rounded-lg overflow-hidden transition-colors">
        <textarea
          ref={textareaRef}
          rows={1}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Poser une question ou demander un diagnostic..."
          disabled={disabled}
          className="w-full bg-transparent text-text-1 text-xs px-3.5 py-2.5 focus:outline-none resize-none max-h-32 min-h-[36px] placeholder:text-text-3 font-normal"
        />
      </div>
      
      <button
        onClick={handleSubmit}
        disabled={disabled || !text.trim()}
        className="h-9 w-9 bg-accent hover:bg-accent-hover text-text-1 rounded-lg flex items-center justify-center shrink-0 shadow shadow-accent/15 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed transition-all duration-150"
      >
        <ArrowUp className="w-4 h-4" />
      </button>
    </div>
  );
};
