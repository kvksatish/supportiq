'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';

interface HelpTooltipProps {
  title: string;
  content: string | string[];
  position?: 'top' | 'bottom' | 'left' | 'right';
  size?: 'xs' | 'sm' | 'md' | 'lg';
}

/**
 *
 */
export default function HelpTooltip({
  title,
  content,
  position = 'top',
  size = 'md'
}: HelpTooltipProps) {
  const [isVisible, setIsVisible] = useState(false);
  const [isHovered, setIsHovered] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [adjustedPosition, setAdjustedPosition] = useState(position);
  const [tooltipStyle, setTooltipStyle] = useState<React.CSSProperties>({});
  const tooltipRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  const contentArray = Array.isArray(content) ? content : [content];

  const calculatePosition = useCallback(() => {
    if (!triggerRef.current) return;

    const triggerRect = triggerRef.current.getBoundingClientRect();
    const tooltipWidth = 320; // minWidth + padding
    const tooltipHeight = 150; // Estimated height
    const gap = 8;
    const padding = 16; // Viewport padding

    let newPosition = position;
    let style: React.CSSProperties = {};

    const spaceTop = triggerRect.top - padding;
    const spaceBottom = window.innerHeight - triggerRect.bottom - padding;
    const spaceLeft = triggerRect.left - padding;
    const spaceRight = window.innerWidth - triggerRect.right - padding;

    if (position === 'top' && spaceTop < tooltipHeight && spaceBottom > tooltipHeight) {
      newPosition = 'bottom';
    } else if (position === 'bottom' && spaceBottom < tooltipHeight && spaceTop > tooltipHeight) {
      newPosition = 'top';
    } else if (position === 'left' && spaceLeft < tooltipWidth && spaceRight > tooltipWidth) {
      newPosition = 'right';
    } else if (position === 'right' && spaceRight < tooltipWidth && spaceLeft > tooltipWidth) {
      newPosition = 'left';
    }

    setAdjustedPosition(newPosition);

    switch (newPosition) {
      case 'top':
        style = {
          left: triggerRect.left + triggerRect.width / 2,
          top: triggerRect.top - gap,
          transform: 'translate(-50%, -100%)',
        };
        break;
      case 'bottom':
        style = {
          left: triggerRect.left + triggerRect.width / 2,
          top: triggerRect.bottom + gap,
          transform: 'translate(-50%, 0)',
        };
        break;
      case 'left':
        style = {
          left: triggerRect.left - gap,
          top: triggerRect.top + triggerRect.height / 2,
          transform: 'translate(-100%, -50%)',
        };
        break;
      case 'right':
        style = {
          left: triggerRect.right + gap,
          top: triggerRect.top + triggerRect.height / 2,
          transform: 'translate(0, -50%)',
        };
        break;
    }

    const finalLeft = style.left as number;
    const finalTop = style.top as number;

    if (typeof finalLeft === 'number' && finalLeft < padding) {
      style.left = padding;
    }
    if (typeof finalTop === 'number' && finalTop < padding) {
      style.top = padding;
    }

    setTooltipStyle(style);
  }, [position]);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (isVisible) {
      calculatePosition();
    }
  }, [isVisible, calculatePosition]);

  useEffect(() => {
    if (!isVisible) return;

    const handleResize = () => {
      if (!tooltipRef.current || !triggerRef.current) return;

      const triggerRect = triggerRef.current.getBoundingClientRect();
      const maxWidth = window.innerWidth - 32;
      const tooltipWidth = Math.min(320, maxWidth);

      let style: React.CSSProperties = {
        maxWidth: `${tooltipWidth}px`,
      };

      switch (position) {
        case 'top':
          style.left = triggerRect.left + triggerRect.width / 2;
          style.top = triggerRect.top - 8;
          style.transform = 'translate(-50%, -100%)';
          break;
        case 'bottom':
          style.left = triggerRect.left + triggerRect.width / 2;
          style.top = triggerRect.bottom + 8;
          style.transform = 'translate(-50%, 0)';
          break;
        case 'left':
          style.left = triggerRect.left - 8;
          style.top = triggerRect.top + triggerRect.height / 2;
          style.transform = 'translate(-100%, -50%)';
          break;
        case 'right':
          style.left = triggerRect.right + 8;
          style.top = triggerRect.top + triggerRect.height / 2;
          style.transform = 'translate(0, -50%)';
          break;
      }

      setTooltipStyle(style);
    };

    handleResize();

    window.addEventListener('resize', handleResize);
    window.addEventListener('scroll', handleResize, true);

    return () => {
      window.removeEventListener('resize', handleResize);
      window.removeEventListener('scroll', handleResize, true);
    };
  }, [isVisible, position]); // Depends only on isVisible and position

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        tooltipRef.current &&
        !tooltipRef.current.contains(event.target as Node) &&
        !triggerRef.current?.contains(event.target as Node)
      ) {
        setIsVisible(false);
      }
    };

    if (isVisible) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [isVisible]);

  const sizeStyles = {
    xs: { fontSize: '12px', lineHeight: '12px' },
    sm: { fontSize: '14px', lineHeight: '14px' },
    md: { fontSize: '16px', lineHeight: '16px' },
    lg: { fontSize: '18px', lineHeight: '18px' },
  };

  const getArrowStyles = () => {
    const baseStyle = {
      position: 'absolute' as const,
      width: '0',
      height: '0',
    };

    const borderColor = 'var(--color-border)';

    switch (adjustedPosition) {
      case 'top':
        return {
          ...baseStyle,
          bottom: '-6px',
          left: '50%',
          transform: 'translateX(-50%)',
          borderLeft: '6px solid transparent',
          borderRight: '6px solid transparent',
          borderTop: `6px solid ${borderColor}`,
        };
      case 'bottom':
        return {
          ...baseStyle,
          top: '-6px',
          left: '50%',
          transform: 'translateX(-50%)',
          borderLeft: '6px solid transparent',
          borderRight: '6px solid transparent',
          borderBottom: `6px solid ${borderColor}`,
        };
      case 'left':
        return {
          ...baseStyle,
          right: '-9px',
          top: '50%',
          transform: 'translateY(-50%)',
          borderTop: '6px solid transparent',
          borderBottom: '6px solid transparent',
          borderLeft: `6px solid ${borderColor}`,
        };
      case 'right':
        return {
          ...baseStyle,
          left: '-9px',
          top: '50%',
          transform: 'translateY(-50%)',
          borderTop: '6px solid transparent',
          borderBottom: '6px solid transparent',
          borderRight: `6px solid ${borderColor}`,
        };
      default:
        return {};
    }
  };

  const tooltipContent = isVisible && (
    <div
      ref={tooltipRef}
      style={{
        position: 'fixed',
        zIndex: 10000,
        minWidth: '280px',
        maxWidth: '400px',
        padding: '16px',
        background: 'var(--color-bg-primary)',
        backdropFilter: 'blur(12px)',
        border: '1px solid var(--color-border)',
        borderRadius: '12px',
        boxShadow: '0 8px 32px rgba(0, 0, 0, 0.4), 0 2px 8px rgba(0, 0, 0, 0.2)',
        ...tooltipStyle,
        animation: 'tooltipFadeIn 0.2s cubic-bezier(0.4, 0, 0.2, 1)',
      }}
    >
      {/* Small arrow */}
      <div style={getArrowStyles()} />

      {/* Title */}
      <div
        style={{
          fontSize: '13px',
          fontWeight: 700,
          color: 'var(--color-accent-primary)',
          marginBottom: '8px',
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
        }}
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
          <circle cx="12" cy="12" r="10" />
          <path d="M12 16v-4" />
          <path d="M12 8h.01" />
        </svg>
        {title}
      </div>

      {/* Content */}
      <div style={{ fontSize: '12px', lineHeight: '1.6', color: 'var(--color-text-secondary)' }}>
        {contentArray.map((item, index) => (
          <div key={index} style={{ marginBottom: index < contentArray.length - 1 ? '8px' : 0 }}>
            {item}
          </div>
        ))}
      </div>

      <style>{`
        @keyframes tooltipFadeIn {
          from {
            opacity: 0;
            transform: ${tooltipStyle.transform || 'translate(-50%, -100%)'} translateY(4px);
          }
          to {
            opacity: 1;
            transform: ${tooltipStyle.transform || 'translate(-50%, -100%)'} translateY(0);
          }
        }
      `}</style>
    </div>
  );

  return (
    <span style={{ position: 'relative', display: 'inline-flex', alignItems: 'flex-start', marginLeft: '4px', verticalAlign: 'top' }}>
      <button
        ref={triggerRef}
        onClick={() => {
          calculatePosition();
          setIsVisible(!isVisible);
        }}
        onMouseEnter={() => {
          calculatePosition();
          setIsVisible(true);
          setIsHovered(true);
        }}
        onMouseLeave={() => {
          setIsVisible(false);
          setIsHovered(false);
        }}
        style={{
          ...sizeStyles[size],
          borderRadius: '50%',
          background: 'transparent',
          border: 'none',
          color: isHovered ? 'var(--color-accent-primary)' : 'var(--color-text-muted)',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontWeight: 500,
          transition: 'color 0.2s ease',
          padding: 0,
          marginTop: size === 'xs' ? '3px' : size === 'sm' ? '2px' : '0',
        }}
        type="button"
      >
        ?
      </button>

      {mounted && createPortal(tooltipContent, document.body)}
    </span>
  );
}
