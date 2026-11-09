#property copyright "Test"
#property strict

int OnInit()
{
   int h1 = FileOpen("test_local.txt", FILE_WRITE|FILE_TXT);
   if(h1 != INVALID_HANDLE) {
      FileWriteString(h1, "Hello from local file in tester\r\n");
      FileClose(h1);
   }
   int h2 = FileOpen("test_common.txt", FILE_WRITE|FILE_TXT|FILE_COMMON);
   if(h2 != INVALID_HANDLE) {
      FileWriteString(h2, "Hello from common file in tester\r\n");
      FileClose(h2);
   }
   return INIT_SUCCEEDED;
}

void OnTick() {}

double OnTester() { return 1.0; }
