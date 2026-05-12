import java.util.regex.Pattern;
import java.util.regex.Matcher;

public class TestVARegexWithCRLF {
    public static void main(String[] args) {
        // Test data with CRLF (from the actual log: 0D 0A at the end)
        String actualDataWithCRLF = "VA,01,28,S,N,-   1.820,   0.000 kg \r\n";
        
        // Current regex pattern from DataParser
        Pattern currentPattern = Pattern.compile(
            "^VA,([0-9]{1,3}),([0-9]{2}),([SUO]),([NG]),([\\+\\-])\\s+([0-9\\.]+),\\s+([0-9\\.]+)\\s+(kg|g|lb|oz)\\s*\\r?\\n?$", 
            Pattern.CASE_INSENSITIVE
        );
        
        System.out.println("Test data with CRLF: '" + actualDataWithCRLF + "'");
        System.out.println("Data length: " + actualDataWithCRLF.length());
        
        // Show detailed character information
        System.out.println("\nCharacter analysis:");
        for (int i = 0; i < actualDataWithCRLF.length(); i++) {
            char c = actualDataWithCRLF.charAt(i);
            if (c == '\r') {
                System.out.printf("Position %2d: '\\r' (ASCII: %d, Hex: %02X)\n", i, (int)c, (int)c);
            } else if (c == '\n') {
                System.out.printf("Position %2d: '\\n' (ASCII: %d, Hex: %02X)\n", i, (int)c, (int)c);
            } else {
                System.out.printf("Position %2d: '%c' (ASCII: %d, Hex: %02X)\n", i, c, (int)c, (int)c);
            }
        }
        
        System.out.println("\nCurrent regex test:");
        Matcher matcher = currentPattern.matcher(actualDataWithCRLF);
        System.out.println("Match result: " + matcher.matches());
        
        if (matcher.matches()) {
            System.out.println("Match successful!");
            for (int i = 1; i <= matcher.groupCount(); i++) {
                System.out.println("Group " + i + ": '" + matcher.group(i) + "'");
            }
        } else {
            System.out.println("Match failed!");
            
            // Try different patterns
            System.out.println("\nTrying other patterns:");
            
            // Pattern without space before kg
            Pattern pattern1 = Pattern.compile(
                "^VA,([0-9]{1,3}),([0-9]{2}),([SUO]),([NG]),([\\+\\-])\\s+([0-9\\.]+),\\s+([0-9\\.]+)\\s+(kg|g|lb|oz)\\s*\\r?\\n?$", 
                Pattern.CASE_INSENSITIVE
            );
            System.out.println("Pattern 1: " + pattern1.matcher(actualDataWithCRLF).matches());
            
            // Pattern with mandatory space before unit
            Pattern pattern2 = Pattern.compile(
                "^VA,([0-9]{1,3}),([0-9]{2}),([SUO]),([NG]),([\\+\\-])\\s+([0-9\\.]+),\\s+([0-9\\.]+)\\s(kg|g|lb|oz)\\s*\\r?\\n?$", 
                Pattern.CASE_INSENSITIVE
            );
            System.out.println("Pattern 2 (mandatory space before unit): " + pattern2.matcher(actualDataWithCRLF).matches());
            
            // Test if the issue is with the space before CRLF
            String trimmedData = actualDataWithCRLF.trim();
            System.out.println("\nTesting trimmed data: '" + trimmedData + "'");
            System.out.println("Trimmed data match: " + currentPattern.matcher(trimmedData).matches());
        }
        
        // Test the exact byte sequence from log
        byte[] hexBytes = {
            0x56, 0x41, 0x2C, 0x30, 0x31, 0x2C, 0x32, 0x38, 0x2C, 0x53, 0x2C, 0x4E, 0x2C, 0x2D, 0x20, 0x20, 
            0x20, 0x31, 0x2E, 0x38, 0x32, 0x30, 0x2C, 0x20, 0x20, 0x20, 0x30, 0x2E, 0x30, 0x30, 0x30, 0x20, 
            0x6B, 0x67, 0x20, 0x0D, 0x0A
        };
        
        String exactData = new String(hexBytes);
        System.out.println("\nTesting exact hex data from log:");
        System.out.println("Exact data: '" + exactData + "'");
        System.out.println("Exact data length: " + exactData.length());
        System.out.println("Exact data match: " + currentPattern.matcher(exactData).matches());
        
        if (currentPattern.matcher(exactData).matches()) {
            Matcher m = currentPattern.matcher(exactData);
            m.matches();
            System.out.println("Exact data match successful! Groups:");
            for (int i = 1; i <= m.groupCount(); i++) {
                System.out.println("Group " + i + ": '" + m.group(i) + "'");
            }
        }
    }
}