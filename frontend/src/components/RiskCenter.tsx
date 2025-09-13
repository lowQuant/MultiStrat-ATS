import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ShieldAlert } from 'lucide-react';

const RiskCenter: React.FC = () => {
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <div className="flex items-center gap-2">
            <ShieldAlert className="h-5 w-5" />
            <CardTitle>Risk Center</CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">This is a placeholder for the Risk Center. Coming soon.</p>
        </CardContent>
      </Card>
    </div>
  );
};

export default RiskCenter;
