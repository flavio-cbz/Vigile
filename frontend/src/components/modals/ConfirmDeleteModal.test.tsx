import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ConfirmDeleteModal } from './ConfirmDeleteModal';

describe('ConfirmDeleteModal', () => {
  it('disables confirmation button when confirmWord is empty string', () => {
    const onConfirm = vi.fn();
    const onClose = vi.fn();
    render(
      <ConfirmDeleteModal
        title="Delete Test"
        message="Are you sure?"
        confirmWord=""
        onConfirm={onConfirm}
        onClose={onClose}
      />,
    );

    const button = screen.getByRole('button', { name: 'Supprimer définitivement' });
    expect(button).toBeDisabled();

    const input = screen.getByRole('textbox');
    fireEvent.change(input, { target: { value: '   ' } });
    expect(button).toBeDisabled();

    fireEvent.click(button);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it('enables confirmation button only when trimmed value matches trimmed confirmWord', () => {
    const onConfirm = vi.fn();
    const onClose = vi.fn();
    render(
      <ConfirmDeleteModal
        title="Delete Test"
        message="Are you sure?"
        confirmWord="my-container"
        onConfirm={onConfirm}
        onClose={onClose}
      />,
    );

    const button = screen.getByRole('button', { name: 'Supprimer définitivement' });
    expect(button).toBeDisabled();

    const input = screen.getByRole('textbox');
    fireEvent.change(input, { target: { value: 'wrong-name' } });
    expect(button).toBeDisabled();

    fireEvent.change(input, { target: { value: '  my-container  ' } });
    expect(button).not.toBeDisabled();

    fireEvent.click(button);
    expect(onConfirm).toHaveBeenCalled();
  });
});
