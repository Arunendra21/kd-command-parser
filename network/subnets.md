# Subnet plan for 10.20.0.0/16

Rule: usable hosts = 2^(32-prefix) - 2. Allocate largest requirement first, each subnet placed right after the previous one, smallest prefix that fits.

## Working

- **app** needs 1000 hosts: smallest 2^n - 2 >= 1000 is 2^10 - 2 = 1022 (2^9 - 2 = 510 is too small), so prefix = 32 - 10 = /22, block size 1024. Next free address 10.20.0.0 is aligned to 1024, so the subnet is 10.20.0.0/22.
- **public** needs 250 hosts: smallest 2^n - 2 >= 250 is 2^8 - 2 = 254 (2^7 - 2 = 126 is too small), so prefix = 32 - 8 = /24, block size 256. Next free address 10.20.4.0 is aligned to 256, so the subnet is 10.20.4.0/24.
- **data** needs 100 hosts: smallest 2^n - 2 >= 100 is 2^7 - 2 = 126 (2^6 - 2 = 62 is too small), so prefix = 32 - 7 = /25, block size 128. Next free address 10.20.5.0 is aligned to 128, so the subnet is 10.20.5.0/25.
- **management** needs 20 hosts: smallest 2^n - 2 >= 20 is 2^5 - 2 = 30 (2^4 - 2 = 14 is too small), so prefix = 32 - 5 = /27, block size 32. Next free address 10.20.5.128 is aligned to 32, so the subnet is 10.20.5.128/27.

Next free address after the four subnets: 10.20.5.160; the rest of 10.20.0.0/16 is unallocated.

## Table

| Subnet | Hosts needed | Network address | Prefix | Usable host range | Broadcast | Usable hosts |
|---|---|---|---|---|---|---|
| app | 1000 | 10.20.0.0 | /22 | 10.20.0.1 to 10.20.3.254 | 10.20.3.255 | 1022 |
| public | 250 | 10.20.4.0 | /24 | 10.20.4.1 to 10.20.4.254 | 10.20.4.255 | 254 |
| data | 100 | 10.20.5.0 | /25 | 10.20.5.1 to 10.20.5.126 | 10.20.5.127 | 126 |
| management | 20 | 10.20.5.128 | /27 | 10.20.5.129 to 10.20.5.158 | 10.20.5.159 | 30 |
