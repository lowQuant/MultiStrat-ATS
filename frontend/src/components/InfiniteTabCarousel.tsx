import React, { useRef, useEffect, useState, useCallback, useLayoutEffect } from 'react';
import { useDragScroll } from '@/hooks/useDragScroll';
import { TabsList, TabsTrigger } from '@/components/ui/tabs';

interface Tab {
  value: string;
  label: string;
}

interface InfiniteTabCarouselProps {
  tabs: Tab[];
  activeTab: string;
  onTabChange: (value: string) => void;
}

const InfiniteTabCarousel: React.FC<InfiniteTabCarouselProps> = ({ tabs, activeTab, onTabChange }) => {
  const { ref: carouselRef } = useDragScroll<HTMLDivElement>();
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const [isSnapping, setIsSnapping] = useState(false);
  const animationFrameId = useRef<number | null>(null);
  const snapBackTimerRef = useRef<number | null>(null);
  const SNAP_BACK_DELAY = 800; // ms after which we snap selected tab to the left (snappier)
  const hasMountedRef = useRef(false);
  const prevScrollLeftRef = useRef(0);

  // Build refs for current tabs order (parent provides selected as first)
  useEffect(() => {
    tabRefs.current = new Array(tabs.length).fill(null);
  }, [tabs]);

  const updateTabStyles = useCallback(() => {
    if (!carouselRef.current) return;
    const container = carouselRef.current;
    const activeIdx = tabRefs.current.findIndex(el => el && el.getAttribute('data-state') === 'active');
    tabRefs.current.forEach((tabElement, i) => {
      if (!tabElement) return;
      const isActive = i === activeIdx;
      // Only selected tab fully emphasized
      tabElement.style.opacity = isActive ? '1' : '0.55';
    });
  }, [carouselRef]);

  // (center snap function removed - not used)

  // Smoothly align the active tab to the left edge (snap-back state)
  const snapActiveToLeft = useCallback(() => {
    const container = carouselRef.current;
    if (!container) return;
    setIsSnapping(true);
    // Snap to the left at the next animation frame to ensure rotated DOM is committed
    requestAnimationFrame(() => {
      container.scrollLeft = 0;
    });
    window.setTimeout(() => {
      setIsSnapping(false);
      updateTabStyles();
    }, 300);
  }, [carouselRef, updateTabStyles]);

  const clearSnapBackTimer = useCallback(() => {
    if (snapBackTimerRef.current !== null) {
      window.clearTimeout(snapBackTimerRef.current);
      snapBackTimerRef.current = null;
    }
  }, []);

  const scheduleSnapBack = useCallback((delay: number = SNAP_BACK_DELAY) => {
    clearSnapBackTimer();
    snapBackTimerRef.current = window.setTimeout(() => {
      snapActiveToLeft();
    }, delay) as unknown as number;
  }, [clearSnapBackTimer, snapActiveToLeft]);

  useLayoutEffect(() => {
    // On selection change (post-mount), immediately snap the active tab to the left.
    if (!hasMountedRef.current) return;
    snapActiveToLeft();
    // Also schedule a re-snap after brief inactivity in case user drags.
    scheduleSnapBack();
  }, [activeTab, snapActiveToLeft, scheduleSnapBack]);

  const handleScroll = () => {
    if (isSnapping || !carouselRef.current) return;

    // User interaction -> reset snap-back timer
    const container = carouselRef.current;
    const prev = prevScrollLeftRef.current;
    const curr = container.scrollLeft;
    const movingRight = curr > prev + 1; // threshold to avoid noise
    prevScrollLeftRef.current = curr;
    // Longer delay whenever moving right; modestly longer when moving left
    scheduleSnapBack(movingRight ? 2000 : 1200);

    if (animationFrameId.current) {
      cancelAnimationFrame(animationFrameId.current);
    }

    animationFrameId.current = requestAnimationFrame(() => {
      updateTabStyles();
    });
  };

  useLayoutEffect(() => {
    // Initial positioning on mount: snap the selected tab to the left immediately.
    if (hasMountedRef.current) return;
    hasMountedRef.current = true;
    const container = carouselRef.current;
    if (container) {
      snapActiveToLeft();
      updateTabStyles();
      scheduleSnapBack();
    }
  }, [snapActiveToLeft, updateTabStyles, scheduleSnapBack]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'ArrowRight') {
        e.preventDefault();
        const currentIndex = tabs.findIndex(t => t.value === activeTab);
        const nextIndex = (currentIndex + 1) % tabs.length;
        onTabChange(tabs[nextIndex].value);
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault();
        const currentIndex = tabs.findIndex(t => t.value === activeTab);
        const prevIndex = (currentIndex - 1 + tabs.length) % tabs.length;
        onTabChange(tabs[prevIndex].value);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [activeTab, onTabChange, tabs]);

  // Cleanup any pending timers on unmount
  useEffect(() => {
    return () => {
      if (snapBackTimerRef.current !== null) {
        window.clearTimeout(snapBackTimerRef.current);
      }
    };
  }, []);

  return (
    <div className="relative w-full bg-muted rounded-md">
      <div
        ref={carouselRef}
        onScroll={handleScroll}
        className="overflow-x-auto no-scrollbar py-2"
        style={{ scrollbarWidth: 'none' }}
      >
        <TabsList key={activeTab} className="inline-flex whitespace-nowrap items-center gap-44 pl-72 pr-24 bg-transparent p-0">
          {tabs.map((tab, index) => (
            <TabsTrigger
              key={tab.value}
              ref={el => tabRefs.current[index] = el}
              value={tab.value}
              onClick={() => onTabChange(tab.value)}
              className="transition-opacity duration-200 text-base data-[state=active]:font-bold data-[state=active]:bg-transparent data-[state=active]:shadow-none"
            >
              {tab.label}
            </TabsTrigger>
          ))}
          {/* Tail spacer to ensure last tab can be fully scrolled into view */}
          <div aria-hidden className="shrink-0 w-72" />
        </TabsList>
      </div>
      {/* No fades */}
    </div>
  );
};

export default InfiniteTabCarousel;
