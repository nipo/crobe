
#define IAP_LOCATION 0x1fff1ff1

void iap_call(void *cmd, void *rsp)
{
    void(*iap_func)(void *cmd, void *rsp) = (void*)IAP_LOCATION;

    iap_func(cmd, rsp);
}
