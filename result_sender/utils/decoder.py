def decode_message(byte_string):
    # mushroom 메시지 형식: "L{라인}S{광전신호 Flag}C{추가 생성 컷}G{그룹}"
    if byte_string.startswith(b"L"):
        try:
            line_index = byte_string.index(b"L")
            count_index = byte_string.index(b"S")
            cut_index = byte_string.index(b"C")
            group_index = byte_string.index(b"G")

            line_value = int(byte_string[line_index + 1 : count_index])
            count_value = int(byte_string[count_index + 1 : cut_index])
            cut_value = int(byte_string[cut_index + 1 : group_index])
            group_value = int(byte_string[group_index + 1 :])
            return line_value, count_value, cut_value, group_value
        except ValueError:
            print("Failed to decode message:", byte_string)
            return None
    else:
        print("Unexpected message format:", byte_string)
        return None
