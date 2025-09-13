import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ClipboardList } from 'lucide-react';

const OrdersView: React.FC = () => {
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <div className="flex items-center gap-2">
            <ClipboardList className="h-5 w-5" />
            <CardTitle>Orders</CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">This is a placeholder for the Orders view. Coming soon.</p>
        </CardContent>
      </Card>
    </div>
  );
};

export default OrdersView;
