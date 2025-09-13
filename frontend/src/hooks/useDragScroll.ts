import { useRef, useEffect, useState } from 'react';

export const useDragScroll = <T extends HTMLElement>() => {
  const ref = useRef<T>(null);
  const [isDragging, setIsDragging] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    let startX: number;
    let scrollLeft: number;

    const onMouseDown = (e: MouseEvent) => {
      // 1. Prevent default text selection and drag behavior
      e.preventDefault();
      
      // 2. Set initial state
      setIsDragging(true);
      el.style.cursor = 'grabbing';
      startX = e.pageX - el.offsetLeft;
      scrollLeft = el.scrollLeft;
    };

    const onMouseMove = (e: MouseEvent) => {
      if (!isDragging) return;
      
      // 1. Prevent default behavior
      e.preventDefault();

      // 2. Calculate new scroll position
      const x = e.pageX - el.offsetLeft;
      const walk = (x - startX) * 1.5; // Multiply for faster scroll
      el.scrollLeft = scrollLeft - walk;
    };

    const onMouseUp = () => {
      setIsDragging(false);
      el.style.cursor = 'grab';
    };

    const onMouseLeave = () => {
      setIsDragging(false);
      el.style.cursor = 'grab';
    };

    // Add event listeners
    el.addEventListener('mousedown', onMouseDown);
    el.addEventListener('mousemove', onMouseMove);
    el.addEventListener('mouseup', onMouseUp);
    el.addEventListener('mouseleave', onMouseLeave);

    // Set initial cursor style
    el.style.cursor = 'grab';

    // Cleanup function
    return () => {
      el.removeEventListener('mousedown', onMouseDown);
      el.removeEventListener('mousemove', onMouseMove);
      el.removeEventListener('mouseup', onMouseUp);
      el.removeEventListener('mouseleave', onMouseLeave);
    };
  }, [isDragging]); // Re-run effect if isDragging changes to re-capture state

  return { ref, isDragging };
};
