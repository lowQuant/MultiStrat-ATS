import React, { useRef, useEffect, useState, useCallback } from 'react';
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

  const extendedTabs = [...tabs, ...tabs, ...tabs];

  const updateTabStyles = useCallback(() => {
    if (!carouselRef.current) return;
    const container = carouselRef.current;
    const containerCenter = container.getBoundingClientRect().left + container.offsetWidth / 2;
    const activeIdx = tabRefs.current.findIndex(el => el && el.getAttribute('data-state') === 'active');
    tabRefs.current.forEach((tabElement, i) => {
      if (!tabElement) return;
      const tabRect = tabElement.getBoundingClientRect();
      const tabCenter = tabRect.left + tabRect.width / 2;
      const distance = Math.abs(containerCenter - tabCenter);
      const isActive = i === activeIdx;
      const isNeighbor = i === activeIdx - 1 || i === activeIdx + 1;

      if (isActive || isNeighbor) {
        tabElement.style.opacity = '1';
      } else {
        const opacity = Math.max(0.25, 1 - distance / 220);
        tabElement.style.opacity = `${opacity}`;
      }
    });
  }, [carouselRef]);

  const snapToTab = useCallback((tabValue: string) => {
    const activeIndex = tabs.findIndex(t => t.value === tabValue);
    if (activeIndex === -1 || !carouselRef.current) return;

    const targetIndex = activeIndex + tabs.length;
    const tabElement = tabRefs.current[targetIndex];
    const container = carouselRef.current;

    if (tabElement && container) {
      setIsSnapping(true);
      const containerCenter = container.offsetWidth / 2;
      const tabCenter = tabElement.offsetLeft + tabElement.offsetWidth / 2;
      const targetScrollLeft = tabCenter - containerCenter;

      container.scrollTo({
        left: targetScrollLeft,
        behavior: 'smooth',
      });

      setTimeout(() => {
        setIsSnapping(false);
        updateTabStyles();
      }, 300);
    }
  }, [tabs, carouselRef, updateTabStyles]);

  useEffect(() => {
    snapToTab(activeTab);
  }, [activeTab, snapToTab]);

  const handleScroll = () => {
    if (isSnapping || !carouselRef.current) return;

    if (animationFrameId.current) {
      cancelAnimationFrame(animationFrameId.current);
    }

    animationFrameId.current = requestAnimationFrame(() => {
      updateTabStyles();

      const { scrollLeft, scrollWidth } = carouselRef.current!;
      const singleSetWidth = scrollWidth / 3;

      if (scrollLeft <= singleSetWidth * 0.5) {
        carouselRef.current!.scrollLeft += singleSetWidth;
      } else if (scrollLeft >= singleSetWidth * 2.5) {
        carouselRef.current!.scrollLeft -= singleSetWidth;
      }
    });
  };

  useEffect(() => {
    const container = carouselRef.current;
    if (container) {
      const activeIndex = tabs.findIndex(t => t.value === activeTab);
      const targetIndex = activeIndex + tabs.length;
      const tabElement = tabRefs.current[targetIndex];

      if (tabElement) {
        const containerCenter = container.offsetWidth / 2;
        const tabCenter = tabElement.offsetLeft + tabElement.offsetWidth / 2;
        container.scrollLeft = tabCenter - containerCenter;
        updateTabStyles();
      }
    }
  }, [activeTab, tabs, updateTabStyles]);

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

  return (
    <div className="relative w-full bg-muted rounded-md">
      <div
        ref={carouselRef}
        onScroll={handleScroll}
        className="overflow-x-auto no-scrollbar py-2"
        style={{ scrollbarWidth: 'none' }}
      >
        <TabsList className="inline-flex whitespace-nowrap items-center gap-14 px-[calc(50%-80px)] bg-transparent p-0">
          {extendedTabs.map((tab, index) => (
            <TabsTrigger
              key={`${tab.value}-${index}`}
              ref={el => tabRefs.current[index] = el}
              value={tab.value}
              onClick={() => onTabChange(tab.value)}
              className="transition-opacity duration-100 text-base text-foreground data-[state=active]:font-bold"
            >
              {tab.label}
            </TabsTrigger>
          ))}
        </TabsList>
      </div>
      {/* Fades on the sides */}
      <div className="pointer-events-none absolute left-0 top-0 h-full w-64 bg-gradient-to-r from-muted to-transparent rounded-l-md" />
      <div className="pointer-events-none absolute right-0 top-0 h-full w-64 bg-gradient-to-l from-muted to-transparent rounded-r-md" />
    </div>
  );
};

export default InfiniteTabCarousel;
