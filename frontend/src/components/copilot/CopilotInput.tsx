import React, { useState, useRef, useEffect } from 'react';
import { useLocale } from '../../i18n';
import { ArrowUp, Square, Sparkles } from 'lucide-react';

interface CopilotInputProps {
  onSend: (message: string) => void;
  disabled?: boolean;
  isStreaming?: boolean;
  onAbort?: () => void;
  suggestions?: string[];
}

export const CopilotInput: React.FC<CopilotInputProps> = ({
  onSend,
  disabled = false,
  isStreaming = false,
  onAbort,
  suggestions = [],
}) => {
  const { t } = useLocale();
  const [text, setText] = useState('');
  const [showSuggestions, setShowSuggestions] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);

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
    setShowSuggestions(false);
  };

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = 'auto';
    textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`;
  }, [text]);

  // Show suggestions popover when the input is focused AND empty.
  useEffect(() => {
    if (text.trim() === '' && suggestions.length > 0) {
      setShowSuggestions(true);
    } else {
      setShowSuggestions(false);
    }
  }, [text, suggestions.length]);

  // Close popover on outside click.
  useEffect(() => {
    if (!showSuggestions) return;
    const handler = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setShowSuggestions(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [showSuggestions]);

  const canSend = !disabled && !isStreaming && text.trim().length > 0;

  return (
    <div
      ref={wrapperRef}
      className="relative p-3 cp-glass border-t border-glass-border shrink-0 font-sans"
    >
      {showSuggestions && suggestions.length > 0 && (
        <div className="absolute bottom-full left-3 right-3 mb-2 cp-glass rounded-lg overflow-hidden shadow-2xl border border-glass-border animate-fade-in">
          <div className="px-3 py-2 border-b border-glass-border flex items-center gap-1.5">
            <Sparkles className="w-3 h-3 text-accent-info-strong" />
            <span className="text-[10px] uppercase tracking-wider font-bold text-text-3 font-interface">
              {t('copilot.suggestions')}
            </span>
          </div>
          <div className="max-h-[200px] overflow-y-auto py-1">
            {suggestions.slice(0, 4).map((sug, idx) => (
              <button
                key={idx}
                onClick={() => {
                  setText(sug);
                  setShowSuggestions(false);
                  textareaRef.current?.focus();
                }}
                className="w-full text-left px-3 py-2 hover:bg-accent-info-soft text-[11.5px] text-text-2 hover:text-text-1 font-sans transition-colors"
              >
                {sug}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="flex items-end gap-2">
        <div className="flex-1 relative flex bg-surface-2 border border-border focus-within:border-accent-info/40 rounded-lg overflow-hidden transition-colors">
          <textarea
            ref={textareaRef}
            rows={1}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={handleKeyDown}
            onFocus={() => text.trim() === '' && suggestions.length > 0 && setShowSuggestions(true)}
            placeholder={isStreaming ? t('copilot.agent_working') : t('copilot.input_placeholder')}
            disabled={disabled}
            className="w-full bg-transparent text-text-1 text-[12px] px-3.5 py-2.5 focus:outline-none resize-none min-h-[36px] placeholder:text-text-3 font-normal"
            style={{ maxHeight: 'var(--copilot-composer-max-height)' }}
            aria-label={t('copilot.input_placeholder')}
          />
        </div>

        {isStreaming ? (
          <button
            onClick={onAbort}
            className="h-9 w-9 bg-severity-critical/20 hover:bg-severity-critical/35 text-severity-critical border border-severity-critical/30 rounded-lg flex items-center justify-center shrink-0 cursor-pointer transition-all duration-150"
            title={t('copilot.abort_tooltip')}
            aria-label={t('copilot.abort_tooltip')}
          >
            <Square className="w-3.5 h-3.5" fill="currentColor" />
          </button>
        ) : (
          <button
            onClick={handleSubmit}
            disabled={!canSend}
            className="h-9 w-9 bg-accent-info hover:bg-accent-info-strong text-bg rounded-lg flex items-center justify-center shrink-0 shadow shadow-accent-info/15 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed transition-all duration-150"
            title={t('copilot.send_tooltip')}
            aria-label={t('copilot.send_tooltip')}
          >
            <ArrowUp className="w-4 h-4" />
          </button>
        )}
      </div>
    </div>
  );
};
