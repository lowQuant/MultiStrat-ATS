import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Database } from 'lucide-react';

const ArcticDBView: React.FC = () => {
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <div className="flex items-center gap-2">
            <Database className="h-5 w-5" />
            <CardTitle>ArcticDB</CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            ArcticDB data view coming soon. We will provide explorers for symbols, libraries, and datasets, with filtering and time range selection.
          </p>
          <div className="mt-4 flex items-center gap-2">
            <Button variant="outline" size="sm" disabled>
              Refresh
            </Button>
            <Button variant="outline" size="sm" disabled>
              Configure
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default ArcticDBView;
