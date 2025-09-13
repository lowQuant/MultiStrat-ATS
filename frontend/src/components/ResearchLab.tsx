import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { FlaskConical } from 'lucide-react';

const ResearchLab: React.FC = () => {
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <div className="flex items-center gap-2">
            <FlaskConical className="h-5 w-5" />
            <CardTitle>Research Lab</CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">This is a placeholder for the Research Lab. Coming soon.</p>
        </CardContent>
      </Card>
    </div>
  );
};

export default ResearchLab;
