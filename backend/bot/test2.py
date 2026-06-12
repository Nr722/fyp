tactical1 = 3+6+10
base1 = 4+4+1+4

tactical2 = 8+4+6
base2 = 4+4+4+3

tactical3 = 6+4+4
base3 = 6+5+4+3

v2tactical1 = 8+5+4+3
v2base1 = 5+5+4

v2tactical2 = 8+6+6+3
v2base2 = 4+4+3

v2tactical3 = 6+6+5+4
v2base3 = 5+4+3

total_tactical = tactical1 + tactical2 + tactical3 + v2tactical1 + v2tactical2 + v2tactical3
total_base = base1 + base2 + base3 + v2base1 + v2base2 + v2base3

# 9 tactical instances in set 1 + 12 in set 2 = 21 total
avg_tactical = total_tactical / 21 
# 12 base instances in set 1 + 9 in set 2 = 21 total
avg_base = total_base / 21         

print(f'avg_tactical: {avg_tactical:.2f}')
print(f'avg_base: {avg_base:.2f}')