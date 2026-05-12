import java.util.regex.Pattern;
import java.util.regex.Matcher;

public class TestRegexWithCRLF {
    public static void main(String[] args) {
        String pattern = "^VA,([0-9]{1,3}),([0-9]{2}),([SUO]),([NG]),([\\+\\-])\\s*([0-9\\.]+),\\s*([0-9\\.]+)\\s*(kg|g|lb)\\s*\\r?\\n?$";
        String dataWithCRLF = "VA,01,28,S,N,-   1.798,   0.000 kg \r\n";
        
        Pattern p = Pattern.compile(pattern, Pattern.CASE_INSENSITIVE);
        Matcher m = p.matcher(dataWithCRLF);
        
        System.out.println("Pattern: " + pattern);
        System.out.println("Data with CRLF: [" + dataWithCRLF.replace("\r", "\\r").replace("\n", "\\n") + "]");
        System.out.println("Data length: " + dataWithCRLF.length());
        System.out.println("Matches: " + m.matches());
        
        if (m.matches()) {
            for (int i = 1; i <= m.groupCount(); i++) {
                System.out.println("Group " + i + ": [" + m.group(i) + "]");
            }
        } else {
            System.out.println("No match found!");
        }
        
        // 测试实际接收到的数据格式
        String actualData = "VA,01,28,S,N,-   1.798,   0.000 kg \r\n";
        Matcher m2 = p.matcher(actualData);
        System.out.println("\nActual data test:");
        System.out.println("Actual data: [" + actualData.replace("\r", "\\r").replace("\n", "\\n") + "]");
        System.out.println("Matches: " + m2.matches());
    }
}