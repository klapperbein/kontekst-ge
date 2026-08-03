input_file = "cc.ka.300.vec"
output_file = "cc.ka.300.small.vec"
max_words = 42000

print("მოდელის ოპტიმიზაცია დაიწყო...")
with open(input_file, 'r', encoding='utf-8') as f_in, open(output_file, 'w', encoding='utf-8') as f_out:
    header = f_in.readline()
    f_out.write(header)
    count = 0
    for line in f_in:
        f_out.write(line)
        count += 1
        if count >= max_words:
            break
print(f"მზადაა! შეიქმნა {output_file}")