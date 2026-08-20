import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { GroupedRadio, ToggleField } from '../form-fields';

// ── GroupedRadio tests ──

describe('GroupedRadio', () => {
  const options = [
    { value: 'auto', label: 'Détection automatique' },
    { value: 'custom', label: 'URL personnalisée' },
  ];

  it('renders all radio options', () => {
    render(
      <GroupedRadio
        name="server_mode"
        options={options}
        value="auto"
        onChange={vi.fn()}
      />
    );
    expect(screen.getByText('Détection automatique')).toBeInTheDocument();
    expect(screen.getByText('URL personnalisée')).toBeInTheDocument();
  });

  it('calls onChange when an option is selected', () => {
    const onChange = vi.fn();
    render(
      <GroupedRadio
        name="server_mode"
        options={options}
        value="auto"
        onChange={onChange}
      />
    );
    fireEvent.click(screen.getByText('URL personnalisée'));
    expect(onChange).toHaveBeenCalledWith('custom');
  });

  it('binds the second field when an option with bind is selected', () => {
    const onChange = vi.fn();
    const onFieldBind = vi.fn();
    const optionsWithBind = [
      { value: 'auto', label: 'Détection automatique' },
      { value: 'custom', label: 'URL personnalisée', bind: { server_url: 'http://192.168.1.1:32400' } },
    ];
    render(
      <GroupedRadio
        name="server_mode"
        options={optionsWithBind}
        value="auto"
        onChange={onChange}
        onFieldBind={onFieldBind}
      />
    );
    fireEvent.click(screen.getByText('URL personnalisée'));
    expect(onChange).toHaveBeenCalledWith('custom');
    expect(onFieldBind).toHaveBeenCalledWith({ server_url: 'http://192.168.1.1:32400' });
  });

  it('does not call onFieldBind when selecting an option without bind', () => {
    const onChange = vi.fn();
    const onFieldBind = vi.fn();
    render(
      <GroupedRadio
        name="server_mode"
        options={options}
        value="auto"
        onChange={onChange}
        onFieldBind={onFieldBind}
      />
    );
    // Click the second option (which has no bind) to verify onFieldBind is not called
    fireEvent.click(screen.getByText('URL personnalisée'));
    expect(onChange).toHaveBeenCalledWith('custom');
    expect(onFieldBind).not.toHaveBeenCalled();
  });

  it('highlights the selected option', () => {
    render(
      <GroupedRadio
        name="server_mode"
        options={options}
        value="custom"
        onChange={vi.fn()}
      />
    );
    const selectedLabel = screen.getByText('URL personnalisée').closest('label');
    expect(selectedLabel).toHaveClass('bg-orange-500/15');
  });
});

// ── ToggleField tests ──

describe('ToggleField', () => {
  it('renders a toggle switch', () => {
    render(
      <ToggleField
        name="live_refresh"
        label="Rafraîchissement live"
        checked={false}
        onChange={vi.fn()}
      />
    );
    expect(screen.getByText('Rafraîchissement live')).toBeInTheDocument();
  });

  it('calls onChange with toggled value', () => {
    const onChange = vi.fn();
    render(
      <ToggleField
        name="live_refresh"
        label="Rafraîchissement live"
        checked={false}
        onChange={onChange}
      />
    );
    fireEvent.click(screen.getByText('Rafraîchissement live'));
    expect(onChange).toHaveBeenCalledWith(true);
  });

  it('renders link variant as a text link button', () => {
    const onChange = vi.fn();
    render(
      <ToggleField
        name="custom_url"
        label="Saisir une adresse IP / URL sur mesure"
        checked={false}
        onChange={onChange}
        variant="link"
      />
    );
    const link = screen.getByText('Saisir une adresse IP / URL sur mesure');
    expect(link.tagName).toBe('BUTTON');
    expect(link).toHaveClass('underline');
    expect(link).toHaveClass('text-orange-400');
  });

  it('toggles the link variant value on click', () => {
    const onChange = vi.fn();
    render(
      <ToggleField
        name="custom_url"
        label="Saisir une adresse IP / URL sur mesure"
        checked={false}
        onChange={onChange}
        variant="link"
      />
    );
    fireEvent.click(screen.getByText('Saisir une adresse IP / URL sur mesure'));
    expect(onChange).toHaveBeenCalledWith(true);
  });

  it('shows checked state in link variant', () => {
    render(
      <ToggleField
        name="custom_url"
        label="Saisir une adresse IP / URL sur mesure"
        checked={true}
        onChange={vi.fn()}
        variant="link"
      />
    );
    const link = screen.getByText('Saisir une adresse IP / URL sur mesure');
    expect(link).toHaveClass('text-orange-300');
  });
});
